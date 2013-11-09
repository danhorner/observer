observer
========
This is a small observer library. There are many, but this one meets my particular needs:

- Straightforward encapsulation of Algorithms that run when input conditions are changed
- Variables can be blocked to suppress updates until inputs have stabilized
    - Never worry about callback ordering
- Observer syntax should be readable

See esp: 

- [py-notify](http://home.gna.org/py-notify/)              (Close, but I esp. want to coalesce updates)
- [trellis](https://pypi.python.org/pypi/Trellis/0.7a2)    (Looks promising, if heavy)

### Sneak Preview: ###

```pycon
>>> def printVar(name):
...     def p(x):
...        print "%s: %r"%(name,x)
...     return p
```

Define a Variable:

```pycon
     >>> v1=Variable(3)
```

Make a derived variable:

```pycon
>>> v2= (v1+3)/5
>>> v2.observe(printVar("v2"))
```

Watch as changes propagate to the derived variable

```pycon
>>> v1.value=27
v2: 6
```

It also works when combining two variables

```pycon
>>> v3 = v2 * 2
>>> v3.observe(printVar("v3"))
>>> v1.value= 12
v2: 3
v3: 6
```

Read on to see how to implement a custom `Algorithm`: a transformation from inputs to outputs that is executed asynchronously as inputs change

### Basic Objects ###

`Observable` exposes the special property `value`, which is implemented by get() and set(). It also implements observe() 

```pycon
>>> o=Observable(1)
>>> o.observe(printVar("o"))
>>> o.value=2
o: 2
```

`Variable` is like `Observable`, but updates can be suppressed using the
`blocked` flag, which is also observable. This is the main building block of
the module: blocking is essential to have updates propagate correctly when
there are diamond-shaped Flows: v1->(v2,v3)->v4
 
```pycon
>>> v=Variable()
>>> v.observe(printVar("v"))
>>> v.value=3
v: 3
>>> v.block()
>>> v.value=4
>>> v.value=5
>>> v.unblock()
v: 5
```

Variables can track other variables unidirectionally

```pycon
>>> source=Variable(2)
>>> v.track_variable(source)
v: 2
>>> source.value=7
v: 7
```

Variables can be linked with other variables bidirectionally

```pycon
>>> v_copy=Variable()
>>> v_copy.observe(printVar("v_copy"))
>>> linkVariables(v,v_copy)
v_copy: 7
>>> source.value="two places at once"
v: 'two places at once'
v_copy: 'two places at once'
>>> unlinkVariables(v,v_copy)
```

`Algorithm` is a container for variables that connects inputs to outputs

```pycon
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
```

These modules can be connected together to form a flow graph. The idea is to
use the `blocked` flag to suppress processing until the parent data has stopped
flapping about. There is also an `enable` flag which is useful to stop your
algorithm from executing until the inputs are connected.

** Todo: ** I don't care about weak references for now. At some point I may add them, but 
** Todo: ** Make block/unblock operations threadsafe
