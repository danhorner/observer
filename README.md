observer
========

Python observer class. Similar to py-notify but simpler. Provides a `Variable` class with support for blocking, and an `Algorithm` class that coalesces updates from blocked inputs

This is a small observer library. There are many, but this one meets my particular needs:

- Straightforward encapsulation of Algorithms that run when input conditions are changed
- Variables can be blocked to suppress updates until inputs have stabilized
	- Never worry about callback ordering
- Observer syntax should be readable

See esp: 

- [py-notify](http://home.gna.org/py-notify/)              (Close, but I esp. want to coalesce updates)
- [trellis](https://pypi.python.org/pypi/Trellis/0.7a2)    (Looks promising, if heavy)


`Observable` exposes the special property `value`, which is implemented by get() and set()

```pycon
>>> def pp(name):
...     def p(x):
...        print "%s: %r"%(name,x)
...     return p

>>> o=Observable(1)
>>> o.observe(pp("o"))
>>> o.value=2
o: 2
```

`Variable` is like `Observable`, but also has an observable `Blocked` flag
 
```pycon
>>> v=Variable()
>>> v.observe(pp("v"))
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
>>> v_copy.observe(pp("v_copy"))
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

>>> i=Inverter()
>>> i.output.observe(pp("inverted"))
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

