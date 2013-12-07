import sys
import string
import re
import types
import copy

import logging
log = logging.getLogger()


# TODO: when doing VAR.get() on a MetaList, all list members that are strings
# should be variable expanded.  Same for MetaDict later on.

# TODO: MetaData.copy()

# TODO: MetaPythonFunc() class

# TODO: MetaShellFunc() class


class MetaDataCacheMiss(Exception):
    pass

class MetaDataRecursiveEval(Exception):
    pass


class MetaDataStack(object):

    def __init__(self):
        self.var = []
        self.deps = []

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

    def clear_deps(self):
        self.deps[-1] = set()

    def add_dep(self, dep):
        if self.deps:
            self.deps[-1].add(dep)

    def add_deps(self, deps):
        if self.deps and deps:
            self.deps[-1] = self.deps[-1].union(deps)

    def __str__(self, prefix='\n  '):
        return prefix.join(self.var)


class MetaData(dict):

    def __init__(self):
        dict.__init__(self)
        self.eval_cache = {}
        self.stack = MetaDataStack()
        MetaList(self, 'OVERRIDES', [])

    def __setitem__(self, key, val):
        assert isinstance(val, MetaVar)
        self.clean(key)
        val.name = key
        dict.__setitem__(self, key, val)

    def __getitem__(self, key):
        var = dict.__getitem__(self, key)
        return var

    def __delitem__(self, key):
        var = dict.__getitem__(self, key)
        self.clean(key)
        var.name = None
        dict.__delitem__(self, key)
        return var
    
    def expand_var_or_raise(self, sub):
        name = sub[2:-1]
        var = dict.__getitem__(self, sub[name])
        return var.get()        
    
    def expand_var_or_leave(self, sub):
        sub = sub.group(0)
        name = sub[2:-1]
        try:
            var = dict.__getitem__(self, name)
        except KeyError:
            self.stack.add_dep(name)
            return sub
        return var.get()        
    
    def expand_var_or_empty(self, sub):
        name = sub[2:-1]
        try:
            var = dict.__getitem__(self, sub[name])
        except KeyError:
            self.stack.add_dep(name)
            return ''
        return var.get()        

    expand_re = re.compile(r'\$\{[a-zA-Z_]+\}')
    def expand(self, value):
        return re.sub(self.expand_re, self.expand_var_or_leave, value)

    def eval(self, value):
        if isinstance(value, types.CodeType):
            value = eval(value, {}, self)
        if isinstance(value, MetaVar):
            value = value.get()
        return value

    def cache(self, value):
        self.eval_cache[self.stack.var[-1]] = (value, self.stack.deps[-1])

    def get_cached(self, var):
        try:
            return self.eval_cache[var]
        except KeyError:
            raise MetaDataCacheMiss(var)

    def clean(self, var):
        try:
            del self.eval_cache[var]
        except KeyError:
            pass
        for (name, (value, deps)) in self.eval_cache.items():
            if var in deps:
                del self.eval_cache[name]


class MetaVar(object):

    __slots__ = [ 'scope', 'name', 'value', 'override_if', ]

    def __new__(cls, scope, name=None, value=None):
        if isinstance(value, basestring):
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
        if isinstance(value, MetaVar):
            value = value.get()
        self.value = value
        assert isinstance(scope, MetaData)
        self.scope = scope
        self.name = name
        if name is not None:
            self.scope[name] = self
        self.override_if = {}

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
        self.value = value

    def get(self):
        if self.name is not None:
            try:
                value, deps = self.scope.get_cached(self.name)
                self.scope.stack.add_dep(self.name)
                self.scope.stack.add_deps(deps)
                return value
            except MetaDataCacheMiss:
                pass
        self.scope.stack.push(self)
        try:
            value = self.scope.eval(self.value)
            if not isinstance(value, self.basetype):
                raise TypeError("invalid type %s in %r"%(type(value), self))
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
                value = self.scope.expand(value)
            if self.name is not None:
                self.scope.cache(value)
        finally:
            self.scope.stack.pop()
        return value


class MetaSequence(MetaVar):

    __slots__ = [ 'prepend', 'append', 'prepends', 'appends',
                  'prepend_if', 'append_if' ]

    def __init__(self, scope, name=None, value=None):
        self.prepends = []
        self.prepend_if = {}
        self.appends = []
        self.append_if = {}
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
        self.prepends.append(value)

    def append(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
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


class MetaString(MetaSequence):

    __slots__ = []

    basetype = basestring

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

    __slots__ = [ 'separator' ]

    basetype = list

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
                    amend_value = self.scope.expand(amend_value)
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
                    amend_value = self.scope.expand(amend_value)
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
                        amend_value = self.scope.expand(amend_value)
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
            ifs = getattr(self, 'ifs', ' \t\n')
            other = re.split('[%s]+'%(ifs), string.strip(other, ifs))
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


import unittest

class TestMetaVar(unittest.TestCase):

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

    def setUp(self):
        pass


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

    def test_set_list_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.set(' foo bar ')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_set_list_bool(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        self.assertRaises(TypeError, VAR.set, (False))

    def test_set_list_int(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        self.assertRaises(TypeError, VAR.set, (42))

    def test_set_list_dict(self):
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

if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
