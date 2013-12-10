import sys
import string
import re
import types
import copy

import logging
log = logging.getLogger()


# FIXME: fix MetaData caching. When any changes are done with .set(),
# .append(), .prepend() cache must be invalidated.  But how do we handle
# override_if, append_if, prepend_if dicts?  We propably need to subclass dict
# for this purpose.

# TODO: MetaData.copy()

# TODO: test if builtin filter() can be used for efficient retrieving list of
# variables with a specific attribute set (True).

# TODO: add_hook() method

# TODO: when doing VAR.get() on a MetaDict, all key and values that are
# strings should be variable expanded.

# TODO: figure out required life-cycle model...  do we need to have
# pickle/unpickle for parallel parse?

# TODO: flatten to json support.  Write to two dicts, one with key to value,
# and another one with key to dict of attributes.  Or one dict, with tuple of
# (value, dict of attributes).

# TODO: MetaPythonFunc() class

# TODO: MetaShellFunc() class

# TODO: include task (True/False) slot/attribute in python and shell func
# classes

# TODO: warn on replace of MetaData variable?  should be using .set() method
# always??


class MetaDataRecursiveEval(Exception):
    pass


class MetaDataStack(object):

    __slots__ = [ 'cache', 'var', 'deps' ]

    def __init__(self, cache):
        self.cache = cache
        self.var = []
        self.deps = []

    def __str__(self, prefix='\n  '):
        return prefix.join(self.var)

    def push(self, var):
        assert isinstance(var, MetaVar)
        if var.name in self.var:
            raise MetaDataRecursiveEval(
                '%s->%s'%('->'.join(self.var), var.name))
        self.var.append(var.name or var)
        self.deps.append(set())

    def pop(self):
        var = self.var.pop()
        deps = self.deps.pop()
        if self.var:
            self.deps[-1].add(var)
            if deps:
                self.deps[-1] = self.deps[-1].union(deps)
        return deps

    def add_dep(self, dep):
        if self.deps:
            self.deps[-1].add(dep)

    def add_deps(self, deps):
        if self.deps and deps:
            self.deps[-1] = self.deps[-1].union(deps)

    def clear_deps(self):
        self.deps[-1] = set()

    def cache_value(self, value):
        self.cache[self.var[-1]] = (value, self.deps[-1])


class MetaDataCache(dict):

    def __setitem__(self, key, value):
        assert isinstance(value, tuple) and len(value) == 2
        dict.__setitem__(self, key, (value[0], list(value[1])))

    def __delitem__(self, key):
        try:
            dict.__delitem__(self, key)
        except KeyError:
            pass
        for (name, (value, deps)) in self.items():
            if key in deps:
                dict.__delitem__(self, name)

    def json_encode(self):
        init = {}
        for (key, (value, deps)) in self.items():
            init[key] = (value, list(deps))
        return { '__jsonclass__': [self.__class__.__name__, [init]] }


class MetaData(dict):

    __slots__ = [ 'cache', 'stack' ]

    def __init__(self, init=None):
        dict.__init__(self)
        if init is None:
            self.cache = MetaDataCache()
            self.stack = MetaDataStack(self.cache)
            MetaList(self, 'OVERRIDES', [])
        elif isinstance(init, MetaData):
            for name,var in init.items():
                var.copy(self)
            self.cache = init.cache.copy()
            self.stack = MetaDataStack(self.cache)
        elif isinstance(init, dict):
            self.cache = MetaDataCache()
            self.stack = MetaDataStack(self.cache)
            for name,var in init.items():
                MetaVar(self, name, var)
            if not 'OVERRIDES' in self:
                MetaList(self, 'OVERRIDES', [])

    def __setitem__(self, key, val):
        assert isinstance(val, MetaVar)
        try:
            del self.cache[key]
        except AttributeError:
            pass # ignore missing cache, ie. during __init__
        val.name = key
        dict.__setitem__(self, key, val)

    def __getitem__(self, key):
        var = dict.__getitem__(self, key)
        return var

    def __delitem__(self, key):
        var = dict.__getitem__(self, key)
        del self.cache[key]
        var.name = None
        dict.__delitem__(self, key)
        return var

    def expand_full(self, sub):
        sub = sub.group(0)
        name = sub[2:-1]
        var = dict.__getitem__(self, name)
        value = var.get()
        if not isinstance(value, basestring):
            raise TypeError(
                "expanded variables must be string: %s is %s"%(
                    name, type(value)))
        return value

    def expand_partial(self, sub):
        sub = sub.group(0)
        name = sub[2:-1]
        try:
            var = dict.__getitem__(self, name)
        except KeyError:
            self.stack.add_dep(name)
            return sub
        value = var.get()
        if not isinstance(value, basestring):
            raise TypeError(
                "expanded variables must be string: %s is %s"%(
                    name, type(value)))
        return value

    def expand_clean(self, sub):
        sub = sub.group(0)
        name = sub[2:-1]
        try:
            var = dict.__getitem__(self, name)
        except KeyError:
            self.stack.add_dep(name)
            return ''
        value = var.get()
        if not isinstance(value, basestring):
            raise TypeError(
                "expanded variables must be string: %s is %s"%(
                    name, type(value)))
        return value

    expand_re = re.compile(r'\$\{[a-zA-Z_]+\}')
    def expand(self, value, method='full'):
        if method == 'full':
            return re.sub(self.expand_re, self.expand_full, value)
        elif method == 'no':
            return value
        elif method == 'partial':
            return re.sub(self.expand_re, self.expand_partial, value)
        elif method == 'clean':
            return re.sub(self.expand_re, self.expand_clean, value)
        raise TypeError("method argument must be string")

    def eval(self, value):
        if isinstance(value, types.CodeType):
            value = eval(value, {}, self)
        if isinstance(value, MetaVar):
            value = value.get()
        return value

    def __repr__(self):
        return "%s()"%(self.__class__.__name__)

    def json_encode(self):
        def metavar_encode(obj):
            return obj.json_encode()
        attrs = { '__jsonclass__': [self.__class__.__name__, []] }
        attrs['cache'] = self.cache.json_encode()
        return json.dumps([attrs, self], default=metavar_encode)

    def json_decode(self, obj):
        try:
            cls = obj.pop('__jsonclass__')
        except KeyError:
            return obj
        if cls == 'MetaData':
            instance = self
        else:
            constructor = eval(cls[0])
            try:
                args = cls[1]
            except IndexError:
                args = []
            try:
                kwargs = cls[2]
            except IndexError:
                kwargs = {}
            if issubclass(constructor, MetaVar):
                name = obj.pop('name')
                instance = constructor(self, name, *args, **kwargs)
            else:
                instance = constructor(*args, **kwargs)
        for name, value in obj.items():
            setattr(instance, name, value)
        return instance


class MetaVarDict(dict):

    __slots__ = [ 'dict', 'var' ]

    def __init__(self, init={}, var=None):
        dict.__init__(self)
        for key, value in init.items():
            self.update(init)
        self.var = var

    def __setitem__(self, key, value):
        del self.var.scope.cache[self.var.name]
        dict.__setitem__(self, key, value)

    def json_encode(self):
        return { '__jsonclass__': [self.__class__.__name__, [None, self.dict]] }


class MetaVar(object):

    __slots__ = [ 'scope', 'name', 'value', 'override_if', 'emit', 'omit' ]

    def __new__(cls, scope, name=None, value=None):
        if cls != MetaVar:
            return super(MetaVar, cls).__new__(cls)
        if isinstance(value, MetaVar):
            return super(MetaVar, value).__new__(type(value))
        elif isinstance(value, basestring):
            return super(MetaVar, cls).__new__(MetaString)
        elif isinstance(value, list):
            return super(MetaVar, cls).__new__(MetaList)
        elif isinstance(value, dict):
            return super(MetaVar, cls).__new__(MetaDict)
        elif isinstance(value, int):
            return super(MetaVar, cls).__new__(MetaInt)
        elif isinstance(value, bool):
            return super(MetaVar, cls).__new__(MetaBool)
        else:
            return super(MetaVar, cls).__new__(MetaString)

    def __init__(self, scope, name=None, value=None):
        assert isinstance(scope, MetaData)
        assert (value is None or
                isinstance(value, self.basetype) or
                isinstance(value, type(self)) or
                isinstance(value, types.CodeType))
        self.scope = scope
        if isinstance(value, MetaVar):
            self.scope = scope
            for attr in MetaVar.__slots__:
                if attr in ('scope', 'name'):
                    continue
                try:
                    setattr(self, attr, getattr(value, attr))
                except AttributeError:
                    pass
        else:
            self.value = value
        self.name = name
        if name is not None:
            self.scope[name] = self
        self.override_if = MetaVarDict()

    def copy(self, scope):
        self.__class__(scope, self.name, self)

    def __setattr__(self, name, value):
        if name in ('override_if', 'prepend_if', 'append_if'):
            value.var = self
        object.__setattr__(self, name, value)

    def __repr__(self):
        return '%s(%r)'%(self.__class__.__name__, self.get())

    def __str__(self):
        return str(self.get())

    def set(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        if not (isinstance(value, self.basetype) or
                isinstance(value, types.CodeType)):
            raise TypeError("cannot set %r object to %s value"%(
                    self, type(value)))
        del self.scope.cache[self.name]
        self.value = value

    def weak_set(self, value):
        if self.value is None:
            del self.scope.cache[self.name]
            return self.set(value)

    def get(self):
        if self.name is not None:
            try:
                value, deps = self.scope.cache[self.name]
            except KeyError:
                pass
            else:
                self.scope.stack.add_dep(self.name)
                self.scope.stack.add_deps(deps)
                return value
        self.scope.stack.push(self)
        try:
            value = self.scope.eval(self.value)
            if not isinstance(value, self.basetype):
                raise TypeError("invalid type %s in %s %s"%(
                        type(value), type(self), self.name))
            if isinstance(self, MetaSequence):
                value = self.amend(value)
            if self.override_if:
                for override in self.scope['OVERRIDES']:
                    if self.override_if.has_key(override):
                        self.scope.stack.clear_deps()
                        value = self.override_if[override]
                        value = self.scope.eval(value)
                        break
                self.scope.stack.add_dep('OVERRIDES')
            if isinstance(self, MetaSequence):
                 value = self.amend_if(value)
            if isinstance(value, basestring):
                value = self.scope.expand(value, method=self.expand)
            if self.name is not None:
                self.scope.stack.cache_value(value)
        finally:
            self.scope.stack.pop()
            pass
        return value

    def json_encode(self):
        import inspect
        slots = set()
        for cls in inspect.getmro(self.__class__):
            try:
                slots.update(cls.__slots__)
            except AttributeError:
                pass
        obj = { '__jsonclass__': [self.__class__.__name__, []] }
        for slot in slots:
            if slot == 'scope':
                continue
            try:
                attr = getattr(self, slot)
                if isinstance(attr, MetaVarDict):
                    obj[slot] = {'__jsonclass__':
                                     [attr.__class__.__name__, [attr]] }
                elif isinstance(attr, dict):
                    obj[slot] = attr.copy()
                elif isinstance(attr, list):
                    obj[slot] = copy.copy(attr)
                elif type(attr) in (str, unicode, int, long, float, bool,
                                    types.NoneType):
                    obj[slot] = attr
            except AttributeError:
                pass
        return obj


class MetaSequence(MetaVar):

    __slots__ = [ 'prepends', 'appends',
                  'prepend_if', 'append_if' ]

    def __init__(self, scope, name=None, value=None):
        if isinstance(value, MetaVar):
            for attr in MetaSequence.__slots__:
                try:
                    setattr(self, attr, getattr(value, attr))
                except AttributeError:
                    pass
        else:
            self.prepends = []
            self.prepend_if = MetaVarDict()
            self.appends = []
            self.append_if = MetaVarDict()
        super(MetaSequence, self).__init__(scope, name, value)

    def __getitem__(self, index):
        return self.get().__getitem__(index)

    def __len__(self):
        return self.get().__len__()

    def __contains__(self, item):
        return self.get().__contains__(item)

    def index(self, sub, start=0, end=None):
        if end is None:
            return self.get().index(sub, start)
        else:
            return self.get().index(sub, start, end)

    def count(self, sub):
        return self.get().count(sub)

    def prepend(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        del self.scope.cache[self.name]
        self.prepends.append(value)

    def append(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        del self.scope.cache[self.name]
        self.appends.append(value)

    def __add__(self, other):
        value = self.get()
        if isinstance(other, type(self)):
            other = other.get()
        elif not isinstance(other, self.basetype):
            raise TypeError(
                "cannot concatenate %s and %s objects"%(
                    type(self), type(other)))
        value += other
        return MetaVar(self.scope, value=value)

    def set(self, value):
        super(MetaSequence, self).set(value)
        self.prepends = []
        self.appends = []

    def weak_set(self, value):
        if self.value is None and not self.prepends and not self.appends:
            del self.scope.cache[self.name]
            return self.set(value)


class MetaString(MetaSequence):

    __slots__ = [ 'expand', 'export' ]

    basetype = basestring

    def __init__(self, scope, name=None, value=None):
        if isinstance(value, MetaVar):
            for attr in MetaString.__slots__:
                try:
                    setattr(self, attr, getattr(value, attr))
                except AttributeError:
                    pass
        else:
            self.expand = 'full'
        super(MetaString, self).__init__(scope, name, value)

    def __str__(self):
        return self.get()

    def count(self, sub, start=None, end=None):
        return self.get().count(sub, start, end)

    def amend(self, value):
        if self.prepends:
            for amend_value in self.prepends:
                amend_value = self.scope.eval(amend_value)
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in self.appends:
                amend_value = self.scope.eval(amend_value)
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        return value

    def amend_if(self, value):
        if self.prepend_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if self.prepend_if.has_key(override):
                    amend_value = self.prepend_if[override]
                    if isinstance(amend_value, MetaVar):
                        amend_value = amend_value.get()
                    if isinstance(amend_value, self.basetype):
                        value = amend_value + value
                    else:
                        raise TypeError(
                            "unsupported prepend_if operation: %s to %s"%(
                                type(amend_value), type(value)))
        if self.append_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if self.append_if.has_key(override):
                    amend_value = self.append_if[override]
                    if isinstance(amend_value, MetaVar):
                        amend_value = amend_value.get()
                    if isinstance(amend_value, self.basetype):
                        value += amend_value
                    else:
                        raise TypeError(
                            "unsupported append_if operation: %s to %s"%(
                                type(amend_value), type(value)))
        return value


class MetaList(MetaSequence):

    __slots__ = [ 'separator', 'expand' ]

    basetype = list

    def __init__(self, scope, name=None, value=None):
        if isinstance(value, MetaVar):
            for attr in MetaString.__slots__:
                try:
                    setattr(self, attr, getattr(value, attr))
                except AttributeError:
                    pass
        else:
            self.expand = 'full'
        super(MetaList, self).__init__(scope, name, value)

    def __iter__(self):
        return self.get().__iter__()

    def __reversed__(self):
        return self.get().__reversed__()

    def split_str(self, value):
        assert isinstance(value, basestring)
        ifs = getattr(self, 'separator', ' \t\n')
        return re.split('[%s]+'%(ifs), string.strip(value, ifs))

    def set(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        if isinstance(value, basestring):
            value = self.split_str(value)
        if not (isinstance(value, self.basetype) or
                isinstance(value, types.CodeType)):
            raise TypeError("cannot set %r object to %s value"%(
                    self, type(value)))
        self.value = value
        self.prepends = []
        self.appends = []

    def amend(self, value):
        value = copy.copy(value)
        if self.prepends:
            for amend_value in self.prepends:
                amend_value = self.scope.eval(amend_value)
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                elif isinstance(amend_value, basestring):
                    amend_value = self.scope.expand(amend_value,
                                                    method=self.expand)
                    value = self.split_str(amend_value) + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in self.appends:
                amend_value = self.scope.eval(amend_value)
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                elif isinstance(amend_value, basestring):
                    amend_value = self.scope.expand(amend_value,
                                                    method=self.expand)
                    value += self.split_str(amend_value)
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        return value

    def amend_if(self, value):
        value = copy.copy(value)
        if self.prepend_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if self.prepend_if.has_key(override):
                    amend_value = self.prepend_if[override]
                    if isinstance(amend_value, MetaVar):
                        amend_value = amend_value.get()
                    if isinstance(amend_value, self.basetype):
                        value = amend_value + value
                    elif isinstance(amend_value, basestring):
                        amend_value = self.scope.expand(amend_value,
                                                        method=self.expand)
                        value = self.split_str(amend_value) + value
                    else:
                        raise TypeError(
                            "unsupported prepend_if operation: %s to %s"%(
                                type(amend_value), type(value)))
        if self.append_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if self.append_if.has_key(override):
                    amend_value = self.append_if[override]
                    if isinstance(amend_value, MetaVar):
                        amend_value = amend_value.get()
                    if isinstance(amend_value, self.basetype):
                        value += amend_value
                    elif isinstance(amend_value, basestring):
                        value += self.split_str(amend_value)
                    else:
                        raise TypeError(
                            "unsupported append_if operation: %s to %s"%(
                                type(amend_value), type(value)))
        return value

    def __add__(self, other):
        value = self.get()
        if isinstance(other, type(self)):
            other = other.get()
        elif isinstance(other, MetaString):
            other = other.get()
        if isinstance(other, basestring):
            other = self.split_str(other)
        elif not isinstance(other, self.basetype):
            raise TypeError(
                "cannot concatenate %s and %s objects"%(
                    type(self), type(other)))
        value += other
        return MetaVar(self.scope, value=value)


class MetaDict(MetaVar):

    def __setitem__(self, key, value):
        self.value[key] = value

    def __delitem__(self, key):
        del self.value[key]

    def __getitem__(self, key):
        return self.value[key] # FIXME: need to do something with the value
                               # returned, ie. eval/expansion...  Better
                               # return the evaluated/expanded value here, and
                               # provide custom access functions for getting
                               # raw values for those special situation where
                               # that might be needed.


class MetaBool(MetaVar):

    def __init__(self, scope, name=None, value=None):
        super(MetaBool, self).__init__(scope, name, value)
        pass


class MetaInt(MetaVar):

    def __init__(self, scope, name=None, value=None):
        super(MetaInt, self).__init__(scope, name, value)
        pass


import json

import unittest


class TestMetaData(unittest.TestCase):

    def setUp(self):
        pass

    def test_metadata_init_default(self):
        d = MetaData()
        self.assertIsInstance(d, MetaData)

    def test_metadata_str(self):
        d = MetaData()
        self.assertIsInstance(str(d), str)

    def test_metadatastack_str(self):
        d = MetaData()
        self.assertEqual(str(d.stack), '')

    def test_metadata_init_metadata(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        self.assertEqual(src['FOO'].get(), 'foo')
        dst = MetaData(src)
        self.assertIsInstance(dst, MetaData)
        src['FOO'].set('bar')
        self.assertEqual(dst['FOO'].get(), 'foo')

    def test_init_dict(self):
        d = MetaData({'FOO': 'foo', 'BAR': 'bar'})
        self.assertEqual(d['FOO'].get(), 'foo')
        d['FOO'].set('bar')
        self.assertEqual(d['FOO'].get(), 'bar')


class TestMetaVar(unittest.TestCase):

    def setUp(self):
        pass

    def test_init_default(self):
        d = MetaData()
        VAR = MetaVar(d)
        self.assertIsInstance(VAR, MetaString)

    def test_init_string(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        self.assertIsInstance(VAR, MetaString)

    def test_init_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, MetaVar(d, value='foo'))
        self.assertIsInstance(VAR, MetaString)

    def test_init_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=[42])
        self.assertIsInstance(VAR, MetaList)

    def test_init_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, MetaVar(d, value=[42]))
        self.assertIsInstance(VAR, MetaString)

    def test_del(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foobar')
        self.assertEqual(d['VAR'].get(), 'foobar')
        del d['VAR']
        with self.assertRaises(KeyError):
            d['VAR']

    def test_cache_set(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['VAR'].set('bar')
        self.assertEqual(d['VAR'].get(), 'bar')

    def test_cache_append(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['VAR'].append('bar')
        self.assertEqual(d['VAR'].get(), 'foobar')

    def test_cache_prepend(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['VAR'].prepend('bar')
        self.assertEqual(d['VAR'].get(), 'barfoo')

    def test_cache_override_if(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['OVERRIDES'].append('USE_bar')
        d['VAR'].override_if['USE_bar'] = 'bar'
        self.assertEqual(d['VAR'].get(), 'bar')

    def test_cache_append_if(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['OVERRIDES'].append('USE_bar')
        d['VAR'].append_if['USE_bar'] = 'bar'
        self.assertEqual(d['VAR'].get(), 'foobar')

    def test_cache_prepend_if(self):
        d = MetaData()
        MetaVar(d, 'VAR', 'foo')
        self.assertEqual(d['VAR'].get(), 'foo')
        d['OVERRIDES'].append('USE_bar')
        d['VAR'].prepend_if['USE_bar'] = 'bar'
        self.assertEqual(d['VAR'].get(), 'barfoo')


class TestMetaString(unittest.TestCase):

    def setUp(self):
        pass

    def test_set_get_str(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set('bar')
        self.assertEqual(VAR.get(), 'bar')

    def test_set_get_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(MetaVar(d, value='bar'))
        self.assertEqual(VAR.get(), 'bar')

    def test_set_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        self.assertRaises(TypeError, VAR.set, (['bar']))

    def test_set_dict(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        self.assertRaises(TypeError, VAR.set, ({'foo': 42}))

    def test_set_bool(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        self.assertRaises(TypeError, VAR.set, (False))

    def test_set_int(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        self.assertRaises(TypeError, VAR.set, (42))

    def test_prepend_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend('foo')
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend('foo')
        VAR.prepend('x')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_prepend_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend(MetaVar(d, value='foo'))
        VAR.prepend(MetaVar(d, value='x'))
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append('bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append('bar')
        VAR.append('x')
        self.assertEqual(VAR.get(), 'foobarx')

    def test_append_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append(MetaVar(d, value='bar'))
        VAR.append(MetaVar(d, value='x'))
        self.assertEqual(VAR.get(), 'foobarx')

    def test_add_str(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR += 'bar'
        self.assertEqual(VAR.get(), 'foobar')

    def test_add_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR += MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_add_self(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR += VAR
        self.assertEqual(VAR.get(), 'foofoo')

    def test_add_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        ADDED = VAR + VAR + VAR
        self.assertEqual(ADDED.get(), 'foofoofoo')

    def test_add_3_mixed(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        ADDED = VAR + 'bar' + VAR
        self.assertEqual(ADDED.get(), 'foobarfoo')

    def test_set_invalid_attr(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_set_code(self):
        d = MetaData()
        VAR = MetaVar(d)
        VAR.set(compile('"foo" + "bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_code(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend(compile('"foo"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_code(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append(compile('"bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_set_code_with_metavars(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        MetaVar(d, 'BAR', 'bar')
        VAR = MetaVar(d)
        VAR.set(compile('FOO + " " + BAR', '<code>', 'eval'))
        value = VAR.get()
        self.assertEqual(value, 'foo bar')

    def test_iter(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        value = ''
        for c in VAR:
            value += c
        self.assertEqual(value, 'foobar')

    def test_override_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.override_if['USE_foo'] = 'foo'
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        self.assertEqual(VAR.get(), 'foo')

    def test_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.override_if['USE_foo'] = 'foo'
        VAR.override_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foo')

    def test_prepend_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        VAR.prepend_if['USE_foo'] = 'foo'
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_bar', 'USE_foo'])
        VAR.prepend_if['USE_foo'] = 'foo'
        VAR.prepend_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foobarx')

    def test_append_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        MetaVar(d, 'OVERRIDES', ['USE_bar'])
        VAR.append_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = 'foo'
        VAR.append_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_metastring_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        self.assertEqual(VAR.get(), 'xfoo')

    def test_append_if_metastring_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        a = MetaVar(d, value='foo')
        a += 'bar'
        VAR.append_if['USE_foo'] = a
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_metastring_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        VAR.append_if['USE_bar'] = MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_str(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertEqual(str(VAR), 'foobar')

    def test_get_invalid_type(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        VAR.set(compile('["foo"]', '<code>', 'eval'))
        self.assertRaises(TypeError, VAR.get, ())

    def test_len(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertEqual(len(VAR), 6)

    def test_contains(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertTrue('f' in VAR)
        self.assertFalse('z' in VAR)

    def test_index(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertEqual(VAR.index('b'), 3)

    def test_count(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertEqual(VAR.count('o'), 2)
        self.assertEqual(VAR.count('r'), 1)

    def test_eval_stack_1(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        MetaVar(d, 'BAR', 'bar')
        MetaVar(d, 'FOOBAR', compile('FOO + BAR', '<code>', 'eval'))
        self.assertEqual(d['FOOBAR'].get(), 'foobar')

    def test_eval_stack_recursive(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', compile('BAR', '<code>', 'eval'))
        BAR = MetaVar(d, 'BAR', compile('FOO', '<code>', 'eval'))
        self.assertRaises(MetaDataRecursiveEval, FOO.get)

    def test_var_expand_default_method(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        self.assertEqual(d['FOO'].expand, 'full')

    def test_var_expand_1(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        MetaVar(d, 'BAR', 'bar')
        MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        self.assertEqual(d['FOOBAR'].get(), 'foobar')

    def test_var_expand_2(self):
        d = MetaData()
        MetaVar(d, 'X', 'x')
        MetaVar(d, 'Y', '${X}y')
        MetaVar(d, 'Z', '${Y}z')
        self.assertEqual(d['Z'].get(), 'xyz')

    def test_var_expand_3(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        MetaVar(d, 'BAR', 'bar')
        MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        self.assertEqual(d['FOOBAR'].get(), 'foobar')
        MetaVar(d, 'FOO', 'xfoox')
        self.assertEqual(d['FOOBAR'].get(), 'xfooxbar')

    def test_var_expand_full(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'full'
        self.assertRaises(KeyError, FOOBAR.get)

    def test_var_expand_partial(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'partial'
        self.assertEqual(d['FOOBAR'].get(), 'foo${BAR}')

    def test_var_expand_clean(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'clean'
        self.assertEqual(d['FOOBAR'].get(), 'foo')

    def test_var_expand_no(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'no'
        self.assertEqual(d['FOOBAR'].get(), '${FOO}${BAR}')

    def test_var_expand_invalid(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'hello world'
        self.assertRaises(TypeError, FOOBAR.get)

    def test_var_expand_override_change(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', '')
        FOO.override_if['USE_foo'] = 'foo'
        self.assertEqual(d['FOO'].get(), '')
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        self.assertEqual(FOO.get(), 'foo')

    def test_var_expand_override(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', '')
        FOO.override_if['USE_foo'] = 'foo'
        MetaVar(d, 'BAR', 'bar')
        MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        self.assertEqual(d['FOO'].get(), '')
        self.assertEqual(d['FOOBAR'].get(), 'bar')
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        self.assertEqual(d['FOO'].get(), 'foo')
        self.assertEqual(d['FOOBAR'].get(), 'foobar')

    def test_var_expand_recursive(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', '${BAR}')
        BAR = MetaVar(d, 'BAR', '${FOO}')
        self.assertRaises(MetaDataRecursiveEval, FOO.get)

    def test_var_expand_full_list(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', [42])
        BAR = MetaVar(d, 'BAR', '${FOO}')
        BAR.expand = 'full'
        self.assertRaises(TypeError, BAR.get)

    def test_var_expand_partial_list(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', [42])
        BAR = MetaVar(d, 'BAR', '${FOO}')
        BAR.expand = 'partial'
        self.assertRaises(TypeError, BAR.get)

    def test_var_expand_clean_list(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', [42])
        BAR = MetaVar(d, 'BAR', '${FOO}')
        BAR.expand = 'clean'
        self.assertRaises(TypeError, BAR.get)

    def test_weak_set_1(self):
        d = MetaData()
        FOO = MetaString(d, 'FOO')
        FOO.weak_set('foo')
        self.assertEqual(FOO.get(), 'foo')

    def test_weak_set_2(self):
        d = MetaData()
        FOO = MetaString(d, 'FOO', 'foo')
        FOO.weak_set('bar')
        self.assertEqual(FOO.get(), 'foo')


class TestMetaList(unittest.TestCase):

    def setUp(self):
        pass

    def test_set_get_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.set(['bar'])
        self.assertEqual(VAR.get(), ['bar'])

    def test_set_get_metalist(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.set(MetaVar(d, value=['bar']))
        self.assertEqual(VAR.get(), ['bar'])

    def test_set_get_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.set(' foo bar ')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_set_bool(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        self.assertRaises(TypeError, VAR.set, (False))

    def test_set_int(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        self.assertRaises(TypeError, VAR.set, (42))

    def test_set_dict(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        self.assertRaises(TypeError, VAR.set, ({'foo': 42}))

    def test_prepend_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        VAR.prepend(['foo'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_prepend_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        VAR.prepend(['foo'])
        VAR.prepend(['x'])
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_prepend_metalist(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        VAR.prepend(MetaVar(d, value=['foo']))
        VAR.prepend(MetaVar(d, value=['x']))
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append(['bar'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append(['bar'])
        VAR.append(['x'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_metalist(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append(['bar', 'x', 'y'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x', 'y'])

    def test_append_string_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append('bar')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_string_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append('bar x')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_string_space(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append(' bar    x ')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_string_tab(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append('\tbar\tx\t')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_string_newline(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.append('\nbar\nx\n')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_add_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += 'bar'
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_add_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += ['bar', 'x']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_set_invalid_attr(self):
        d = MetaData()
        VAR = MetaVar(d, value=[])
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_iter(self):
        d = MetaData()
        VAR = MetaVar(d, value=[1,2,3])
        sum = 0
        for i in VAR:
            sum += i
        self.assertEqual(sum, 6)

    def test_iter_reversed(self):
        d = MetaData()
        VAR = MetaVar(d, value=[1,2,3])
        value = None
        for i in reversed(VAR):
            if value is None:
                value = i
            else:
                value = value - i
        self.assertEqual(value, 0)

    def test_override_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        VAR.override_if['USE_foo'] = ['foo']
        self.assertEqual(VAR.get(), ['foo'])

    def test_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=[])
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.override_if['USE_foo'] = ['foo']
        VAR.override_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo'])

    def test_prepend_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        MetaVar(d, 'OVERRIDES', ['USE_foo'])
        VAR.prepend_if['USE_foo'] = ['foo']
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_prepend_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        MetaVar(d, 'OVERRIDES', ['USE_bar', 'USE_foo'])
        VAR.prepend_if['USE_foo'] = ['foo']
        VAR.prepend_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        MetaVar(d, 'OVERRIDES', ['USE_bar'])
        VAR.append_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = ['foo']
        VAR.append_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_if_metalist_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = MetaVar(d, value=['foo'])
        self.assertEqual(VAR.get(), ['x', 'foo'])

    def test_append_if_metastring_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        a = MetaVar(d, value=['foo'])
        a += ['bar']
        VAR.append_if['USE_foo'] = a
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_if_metastring_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        MetaVar(d, 'OVERRIDES', ['USE_foo', 'USE_bar'])
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        VAR.append_if['USE_bar'] = MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foobar'])
        self.assertEqual(str(VAR), "['foobar']")

    def test_len(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar'])
        self.assertEqual(len(VAR), 2)

    def test_contains(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar'])
        self.assertTrue('foo' in VAR)
        self.assertFalse('hello' in VAR)

    def test_contains_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar', 'hello'])
        self.assertEqual(VAR.index('hello'), 2)

    def test_contains_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar', 'hello'])
        self.assertRaises(ValueError, VAR.index, ('foo', 1))

    def test_contains_3(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar', 'hello'])
        self.assertEqual(VAR.index('hello', end=3), 2)

    def test_contains_4(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar', 'hello'])
        with self.assertRaises(ValueError):
            VAR.index('hello', end=1)

    def test_count(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar', 'hello', 'foo', 'bar'])
        self.assertEqual(VAR.count('hello'), 1)
        self.assertEqual(VAR.count('foo'), 2)

    def test_string_expand(self):
        d = MetaData()
        VAR = MetaVar(d, value=[])
        MetaVar(d, 'FOO', 'f o o')
        MetaVar(d, 'BAR', 'b a r')
        MetaVar(d, 'FOOBAR', "${FOO} ${BAR}")
        VAR.append("${FOOBAR}")
        self.assertEqual(VAR.get(), ['f', 'o', 'o', 'b', 'a', 'r'])

    def test_weak_set_1(self):
        d = MetaData()
        FOO = MetaList(d, 'FOO', None)
        FOO.weak_set(['foo'])
        self.assertEqual(FOO.get(), ['foo'])

    def test_weak_set_2(self):
        d = MetaData()
        FOO = MetaList(d, 'FOO', ['foo'])
        FOO.weak_set(['bar'])
        self.assertEqual(FOO.get(), ['foo'])


class TestJSON(unittest.TestCase):

    def setUp(self):
        pass

    def test_json_1(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        self.assertEqual(dst['FOO'].get(), 'foo')

    def test_json_appends(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append('bar')
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_json_prepends(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'bar')
        src['FOO'].prepend('foo')
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_json_override_if(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].override_if['USE_bar'] = 'bar'
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'foo')
        self.assertEqual(dst['FOO'].get(), 'bar')

    def test_json_prepend_if(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'bar')
        src['FOO'].prepend_if['USE_bar'] = 'foo'
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'bar')
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_json_append_if(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append_if['USE_bar'] = 'bar'
        dst = MetaData()
        json.loads(src.json_encode(), object_hook=dst.json_decode)
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'foo')
        self.assertEqual(dst['FOO'].get(), 'foobar')

if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
