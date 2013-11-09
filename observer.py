# observer.py
# The MIT License (MIT)
# 
# Copyright (c) 2013 Daniel Horner
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
This is a small observer library. There are many, but this one meets my particular needs:

- Straightforward encapsulation of Algorithms that run when input conditions are changed
- Variables can be blocked to suppress updates until inputs have stabilized
    - Never worry about callback ordering
- Observer syntax should be readable

See esp: 

- [py-notify](http://home.gna.org/py-notify/)              (Close, but I esp. want to coalesce updates)
- [trellis](https://pypi.python.org/pypi/Trellis/0.7a2)    (Looks promising, if heavy)

Sneak Preview:

     >>> def printVar(name):
     ...     def p(x):
     ...        print "%s: %r"%(name,x)
     ...     return p

Define a Variable:
     >>> v1=Variable(3)

Make a derived variable:
     >>> v2= (v1+3)/5
     >>> v2.observe(printVar("v2"))

Watch as changes propagate to the derived variable
     >>> v1.value=27
     v2: 6

It also works when combining two variables
     >>> v3 = v2 * 2
     >>> v3.observe(printVar("v3"))
     >>> v1.value= 12
     v2: 3
     v3: 6

### Basic Objects ###

`Observable` exposes the special property `value`, which is implemented by get() and set(). It also implements observe() 

     >>> o=Observable(1)
     >>> o.observe(printVar("o"))
     >>> o.value=2
     o: 2

`Variable` is like `Observable`, but updates can be suppressed using the
`blocked` flag, which is also observable. blocking is essential to have updates
propagate correctly when there are diamond-shaped Flows: v1->(v2,v3)->v4
 
     >>> v=Variable()
     >>> v.observe(printVar("v"))
     >>> v.value=3
     v: 3
     >>> v.block()
     >>> v.value=4
     >>> v.value=5
     >>> v.unblock()
     v: 5

Variables can track other variables unidirectionally

    >>> source=Variable(2)
    >>> v.track_variable(source)
    v: 2
    >>> source.value=7
    v: 7

Variables can be linked with other variables bidirectionally

    >>> v_copy=Variable()
    >>> v_copy.observe(printVar("v_copy"))
    >>> linkVariables(v,v_copy)
    v_copy: 7
    >>> source.value="two places at once"
    v: 'two places at once'
    v_copy: 'two places at once'
    >>> unlinkVariables(v,v_copy)


`Algorithm` is a container for variables that connects inputs to outputs

    >>> class Inverter(Algorithm):
    ...     _inputs_=('input',)
    ...     _outputs_=('output',)
    ...     def update(self):
    ...         self.output.value=not self.input.value
     
    >>> i=Inverter(enabled=False)
    >>> i.output.observe(printVar("inverted"))
    >>> i.enabled.set(True)
    inverted: True
    >>> i.input.value=True
    inverted: False
 
These modules can be connected together to form a flow graph. The idea is to
use the `blocked` flag to suppress processing until the parent data has stopped
flapping about. There is also an `enable` flag which is useful to stop your
algorithm from executing until the inputs are connected.

# ** Todo: ** I don't care about weak references for now. At some point I may add them, but 
# ** Todo: ** Make block/unblock operations threadsafe
"""

__all__=(

'Observable', 'Variable', 'IdentityVariable', 'AlwaysUpdateVariable',

'Algorithm', 'Add', 'Subtract', 'Multiply', 'Divide',

'linkVariables', 'unlinkVariables',

'variable_operation',

'any_var_is_none','debugVariable', 'pp',

)


import functools
import operator

from contextlib import contextmanager

#Set __DEBUG__ to true to track the nesting level. This is a bit slower. The pretty-printing function can use it 
__DEBUG__ = False 
_nest_level=0

def adderExample():
    """
    Simple example. Returns a tuple containing two cascaded adders and three input variables that feed them.
    """
    class Adder(Algorithm):
        _inputs_=('a','b')
        _outputs_=('c',)
        def __init__(self,name):
            self.name=name
            self.a=Variable(0)
            self.b=Variable(0)
            self.c=Variable(0)
            Algorithm.__init__(self)
            self.enabled.value=True
    
        def update(self):
            self.c.value=self.a.value+self.b.value

    a1=Adder("a1")
    a2=Adder("a2")
    i1,i2,i3=Variable(0),Variable(0),Variable(0)

    a2.c.observe(pp("a2.c value"))
    a2.c.blocked.observe(pp("a2.c blocked"))
    a1.c.observe(pp("a1.c value"))
    a1.c.blocked.observe(pp("a1.c blocked"))

    a2.a.track_variable(a1.c)
    a1.a.track_variable(i1)
    a1.b.track_variable(i2)
    a2.b.track_variable(i3)

    return ((i1,i2,i3),(a1,a2))


class Observable(object):
    """
    The basic type. An observable value. 
    You can customize the equality test to change when observers get notified. 

        Standard get/set methods
        >>> o=Observable()
        >>> o.set(1)
        >>> print o.get()
        1

        Also available as a value property:
        >>> o.value
        1
        >>> o.value=2
        

        Define a pretty printer for this example:
        >>> def p(value):
        ...     print("value changed: %r"%(value,))
        ...

        Observe the value of a variable with a callback
        >>> o.observe(p)
        >>> o.set(3)
        value changed: 3

        The callback is not called unless the vlaue changes
        >>> o.set(3)
        >>> o.value=4
        value changed: 4

        Or you call it explicitly
        >>> o.notify_observers()
        value changed: 4

        >>> o.unobserve(p)
        >>> o.value=5
        >>> o.value
        5
    """
    __slots__ = ('observers','_value')
    
    equality_test=operator.eq

    def __init__(self,initialValue=None):
        self.observers=[]
        self._value=initialValue
        
    def observe(self,callback):
        self.observers.append(callback)
        
    def unobserve(self,callback):
        self.observers.remove(callback)
        
    def get(self):
        return self._value
    
    def set(self,value):
        try:
            changed=not self.equality_test(self._value,value)
        except:
            print "Equality Test Error in class %r: (%r),(%r)"%(self.__class__,self._value,value)
            raise

        if changed:
            self._value=value
            self.notify_observers()

    def notify_observers(self):
        for o in self.observers:
            o(self._value)

            
    if __DEBUG__:
        _notify_observers=notify_observers

        def notify_observers(self):
            if __DEBUG__:
                globals()['_nest_level'] += 1

            for o in self.observers:
                o(self._value)

            if __DEBUG__:
                globals()['_nest_level'] -= 1
                
    value = property(get,set) 


class Variable(Observable):
    """
    This variable also encapsulates second variable to be used as a "blocked" flag. 
    When the Variable is blocked, the value is cached in pendingValue until it has been unblocked again.
    At that point, any changes to value are applied and observers get notified. 

        Define a pretty-printer
        >>> def p(name):
        ...     def q(value):
        ...         print "%s: %r"%(name,value)
        ...     return q

        Same semantics as Observable
        >>> v=Variable(3)
        >>> print v.get()
        3
        >>> print v.value
        3

        But also contains and obsevable blocked flag
        >>> v.blocked.observe(p("BLOCKED"))
        >>> v.observe(p("VALUE"))
        >>> v.value="hello"
        VALUE: 'hello'
        >>> v.block()
        BLOCKED: True
        >>> v.value=17
        >>> v.value=18
        >>> v.unblock()
        VALUE: 18
        BLOCKED: False

        updates_coalesced is a context-manager that automatically blocks and unblocks the Variable
        use this when you will be changing the value and don't want to notify observers
        >>> with v.updates_coalesced():
        ...     v.value="Hello"
        ...     v.value="You won't see this"
        ...     v.value="You will see this"
        BLOCKED: True
        VALUE: 'You will see this'
        BLOCKED: False

        You can have this variable track another one. Both the value and the blocked flag are propagated
        >>> another_var=Variable(3)
        >>> v.track_variable(another_var)
        VALUE: 3
        >>> another_var.block()
        BLOCKED: True
        >>> another_var.value=155
        >>> another_var.unblock()
        VALUE: 155
        BLOCKED: False

    """
    __slots__=('blocked','pendingValue')
    
    def __init__(self,initialValue=None):
        self.pendingValue=None
        self.blocked=Observable(False)
        Observable.__init__(self,initialValue)
        
    def block(self):
        if self.blocked.value == False:
            self.pendingValue=self.value
            self.blocked.set(True)
        
    def unblock(self):
        if self.blocked.value == True:
            self._set(self.pendingValue)
            self.blocked.set(False)
        
    def setBlocked(self,blocked):
        if blocked:
            self.block()
        else:
            self.unblock()
            
    @contextmanager
    def updates_coalesced(self):
        self.block()
        yield
        self.unblock()
        
    def _set(self,value):
        super(Variable,self).set(value)  # set value, bypassing blocked check
        
    def set(self,value):
        """
        set value, or cache it if currently blocked
        """
        if self.blocked.value:
            self.pendingValue=value
        else:
             self._set(value)
                
    def get(self):
        if self.blocked.value:
            return self.pendingValue
        else:
            return super(Variable,self).get()  

    def track_variable(self,sourceVar):
        sourceVar.blocked.observe(self.setBlocked)
        sourceVar.observe(self.set)
        self.set(sourceVar.value)
        
    def stop_tracking_variable(self,sourceVar):
        sourceVar.blocked.unobserve(self.setBlocked)
        sourceVar.unobserve(self.set)
        self.blocked.value=False
                           
    def __add__(self,x):
        return variable_operation(Add,self,x)
    def __sub__(self,x):
        return variable_operation(Subtract,self,x)
    def __mul__(self,x):
        return variable_operation(Multiply,self,x)
    def __div__(self,x):
        return variable_operation(Divide,self,x)

    value = property(get,set) 
        
class IdentityVariable(Variable):
    """
    >>> a1=["123"]
    >>> a2=["123"]
    >>> b1="123"
    >>> b2="123"
    >>> v1=IdentityVariable()
    >>> debugVariable(v1,"v1")
    >>> v1.value=a2
    v1 value: ['123']
    >>> v1.value=a1
    v1 value: ['123']
    >>> v1.value=b1
    v1 value: '123'
    >>> v1.value=b2
    """
    equality_test=operator.is_

class AlwaysUpdateVariable(Variable):
    """
    >>> v1=AlwaysUpdateVariable()

    >>> debugVariable(v1,"v1")
    >>> v1.value=3
    v1 value: 3
    >>> v1.value=3
    v1 value: 3
    """
    equality_test=lambda self,a,b: False
def linkVariables(v1,v2):
    """
    Create a bidirectional link between v1 and v2.
    The synchronized value depends on the blocked state:
        If v1 isn't blocked, its value is propagated to v2
        If v2 isn't blocked, its value is propageted to v1
        If they're both blocked, nothing happens until on variable is unblocked

    The variables are blocked as a group.

    Note that it's not safe to link variables where equality_test always returns False. 
    Note that linking variables creates a cycle. if you don't unlink them later, you will leak memory

        Define a pretty printer for this example 
        >>> def p(name):
        ...     def q(value):
        ...         print "%s: %r"%(name,value)
        ...     return q


        >>> v1=Variable(3)
        >>> v2=Variable(4)
        >>> v1.observe(p("V1"))
        >>> v2.observe(p("V2"))
        >>> v1.blocked.observe(p("V1 BLOCKED"))
        >>> v2.blocked.observe(p("V2 BLOCKED"))
        >>> linkVariables(v1,v2)
        V2: 3
        >>> print "v1: %r v2: %r"%(v1.value,v2.value)
        v1: 3 v2: 3
        >>> v1.value=6
        V1: 6
        V2: 6

        When unblocking linked variables, the eventual value will come from the
        one that is unblocked first.

        Keep V2's value: 
        >>> v2.block()
        V2 BLOCKED: True
        V1 BLOCKED: True
        >>> v2.value=19
        >>> v2.value=20
        >>> v1.value=18
        >>> v2.value=21
        >>> v2.unblock()
        V2: 21
        V2 BLOCKED: False
        V1: 21
        V1 BLOCKED: False

        Keep V1's value:
        >>> with v1.updates_coalesced():  #Variables diverge while blocked. v1's value is kept
        ...     v2.value=22
        ...     v1.value=23
        ...     v2.value=24
        V1 BLOCKED: True
        V2 BLOCKED: True
        V1: 23
        V1 BLOCKED: False
        V2: 23
        V2 BLOCKED: False

        >>> 
        >>> unlinkVariables(v1,v2) #Break the cycle for GC
        >>> v1.value=7
        V1: 7

    """
    v2.track_variable(v1)
    v1.track_variable(v2)
    
def unlinkVariables(v1,v2):
    v1.stop_tracking_variable(v2)
    v2.stop_tracking_variable(v1)


def _get_variable_constructors(attributes,defaultType=Variable):
    """
    Used internally by Algorithm constructor to handle the _inputs_ and _outputs_ lists

    attributes: each attribute can be a string, which becomes a variable name, 
                or tuple (name,constructor)
    returns: a list of pairs (attributeName, Constructor)
    """
    def get_constructor(attr):
        if type(attr) == tuple:
            return(attr)
        else:
            return(attr,defaultType)
        
    return map(get_constructor,attributes)
               
class Algorithm(object):
    """
    A container for input and output variables.  
    To use, you must inherit from `Algorithm`   

    Create class attributes `_inputs_` and `_outputs`, and the Algorithm default constructor will populate them with Variable() instances. 
    Or initialize the variables yourself before calling the inherited constructor and it will leave them alone. 
    
    In either case, it will bind  inputs to call the update() function on change
    It will also bind the valid flags to update into a central _valid_ object on the instance. 

    There is a central enable() flag that is set to true by default.
    If you need to bind values into the inputs before running the algorithm,
    then set it to true in the constructor or by setting the class variable
    `_start_enabled_`

        Define a pretty printer for this example 
        >>> def p(name):
        ...     def q(value):
        ...         print "%s: %r"%(name,value)
        ...     return q

        Your code goes in a subclass of Algorithm
        >>> class  Adder(Algorithm):
        ...     _inputs_=('a','b')
        ...     _outputs_=('c',)
        ...     _start_enabled_=False
        ...
        ...     def update(self):
        ...         self.c.value = self.a.value + self.b.value

        Input and output variables are automatically created
        >>> adder=Adder()
        >>> adder.a.observe(p("a"))
        >>> adder.b.observe(p("b"))
        >>> adder.c.observe(p("c"))
        >>> adder.a.value=1
        a: 1
        >>> adder.b.value=1
        b: 1
        >>> adder.enabled.value=1
        c: 2
        >>> adder.a.value=2
        c: 3
        a: 2

        Explicit update forces the algorithm to run even if disabled
        >>> adder.enabled.set(False)
        >>> adder.a=None
        >>> adder.update() 
        Traceback (most recent call last):
            File "<doctest __main__.Algorithm[1]>", line 6, in update
            self.c.value = self.a.value + self.b.value
        AttributeError: 'NoneType' object has no attribute 'value'

    """
    __slots__=("_inputs_","_outputs_","inputs","outputs","enabled","outputs_blocked")
    __variableType__=Variable
    _start_enabled_=True
    _outputs_=tuple()
    _inputs_=tuple()
    
    def __init__(self,enabled=None,**kwargs):
        if enabled is None:
            enabled=self._start_enabled_

        self.updatePending=False
        self.outputs_blocked=Observable(False)
        
        self.enabled=Observable(enabled)
        self.enabled.observe(self.check_blocks_and_update)
        
        assert isinstance(self._inputs_,(tuple,list))
        for attrName,constructor in _get_variable_constructors(self._inputs_):
            if hasattr(self,attrName):
                inputVariable=getattr(self,attrName,None)
            elif attrName in kwargs: 
                inputVariable=constructor(kwargs[attrName])
            else:
                inputVariable=constructor()

            setattr(self,attrName,inputVariable)
            
            inputVariable.blocked.observe(self.check_blocks_and_update)
            inputVariable.observe(self.check_blocks_and_update)

        assert isinstance(self._outputs_,(tuple,list))
        for attrName,constructor in _get_variable_constructors(self._outputs_):  
            if hasattr(self,attrName):
                outputVariable=getattr(self,attrName,None)
            elif attrName in kwargs: 
                outputVariable=constructor(kwargs[attrName])
            else:
                outputVariable=constructor()
            setattr(self,attrName,outputVariable)
            
            self.outputs_blocked.observe(outputVariable.setBlocked)

        self.inputs=[getattr(self,n) for n,t in _get_variable_constructors(self._inputs_) ]
        self.outputs=[getattr(self,n) for n,t in _get_variable_constructors(self._outputs_) ]
            
        self.check_blocks_and_update()
   
    def update(self):
        pass
    
    def check_blocks_and_update(self,dummy=None):
        isBlocked= not(self.enabled.value) or any(map(lambda i: i.blocked.value, self.inputs))      
        if not isBlocked:
            self.update()

        self.outputs_blocked.value = isBlocked
        

    def observe(self,attribute,callback):
        getattr(self,'_' + attribute).observe(callback)
        
    def unobserve(self,attribute,callback):
        getattr(self,'_' + attribute).unobserve(callback)
        
    def get(varname,self):
        variable=getattr(self,varname)
        return variable.value
    
    def set(varname,self,value):
        variable=getattr(self,varname)
        variable.value=value

def pp(name):
    def p(x):
        print "%s%s: %r"%(('-')*_nest_level,name,x)
        return x
    return p
    
def debugVariable(v,name):
    def blockWatch(b):
        assert(v.equality_test(v.value,v.pendingValue)) # Someone tried to manipulate blocked flag directly
        print (('-') * _nest_level) + name + " blocked: " + repr(b) + (" value: [%r]"%(v.value,))
    v.observers.insert(0,pp(name + " value"))
    v.blocked.observers.insert(0,blockWatch)
    



class Subtract(Algorithm):
    """
    >>> sub=Subtract(a=1,b=3)
    >>> sub.a.value
    1
    >>> sub.b.value
    3
    >>> sub.c.value
    -2
    """
    _inputs_=('a','b')
    _outputs_=('c',)
    def update(self):
        if any_var_is_none(self.inputs):
            self.c.value=None
        else:
            self.c.value=(self.a.value - self.b.value)

class Add(Algorithm):
    _inputs_=('a','b')
    _outputs_=('c',)
    def update(self):
        if any_var_is_none(self.inputs):
            self.c.value=None
        else:
            self.c.value=self.a.value + self.b.value

class Multiply(Algorithm):
    _inputs_=('a','b')
    _outputs_=('c',)
    def update(self):
        if any_var_is_none(self.inputs):
            self.c.value=None
        else:
            self.c.value=self.a.value * self.b.value

class Divide(Algorithm):
    _inputs_=('a','b')
    _outputs_=('c',)
    def update(self):
        if any_var_is_none(self.inputs):
            self.c.value=None
        else:
            self.c.value=self.a.value / self.b.value

def variable_operation(algorithm,*inputs):
    """

    Doesn't handle IdentityVariable yet: That is, the inputs are not of the
    correct type, so identity_operation will throw on numpy arrays

    >>> v1=Variable(3)
    >>> v2=Variable(1)

    >>> sub=Subtract(a=3,b=1)
    >>> sub.a.value
    3
    >>> sub.b.value
    1
    >>> sub.c.value
    2


    >>> v3=variable_operation(Subtract,v1,v2)
    >>> v3.value
    2

    >>> v1.value=0
    >>> v3.value
    -1
    """
    a=algorithm()
    for input,algorithm_input in zip(inputs,a.inputs):
        if isinstance(input,Variable):
            algorithm_input.track_variable(input)
        else:
            algorithm_input.value=input

    return a.outputs[0]

def __test_propagation():
    """
    Show that update coalescing actually works

    >>> ((i1,i2,i3),(a1,a2))=adderExample()

    >>> i1.value=1  
    a1.c value: 1
    a2.c value: 1

    >>> with i1.updates_coalesced():
    ...     with i2.updates_coalesced():
    ...         with i3.updates_coalesced():
    ...             i1.value,i2.value,i3.value=(6,5,4)
    ...
    a1.c blocked: True
    a2.c blocked: True
    a1.c value: 11
    a1.c blocked: False
    a2.c value: 15
    a2.c blocked: False
    """
    pass

def __test_algorithm():
    """
        >>> class AddOne(Algorithm):
        ...    _inputs_=('input',)
        ...    _outputs_=('output',)
        ...    def update(self):
        ...        self.output.value=1+(self.input.value or 0)
        ...
        ...    def __init__(self,input=0):
        ...        Algorithm.__init__(self,enabled=True,input=input)

        
        >>> i=AddOne()
        >>> debugVariable(i.output,"i.output")
        >>> i.input.value=1
        i.output value: 2
        >>> with i.input.updates_coalesced():
        ...     i.input.value=3
        ...     i.input.value=4
        i.output blocked: True value: [2]
        i.output value: 5
        i.output blocked: False value: [5]

    Shows how to initialize variables
        >>> j=AddOne(input=3)
        >>> j.output.value
        4

    """

def __test_variable_operations():
    """
        >>> v1=Variable(0)
        >>> debugVariable(v1,"v1")
        >>> v2=v1+1
        >>> debugVariable(v2,"v2")
        >>> v1.value=10    
        v1 value: 10
        v2 value: 11

        >>> v3=Variable(0)
        >>> v4=v1*v3
        >>> debugVariable(v4,"v4")
        >>> v3.value=5
        v4 value: 50

    """
def any_var_is_none(l):
    return any(map(lambda i: i.value is None,l))


if __name__ == "__main__":
    import doctest
    doctest.testmod()
