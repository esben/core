import sys
import string
import re
import types
import copy

import logging
log = logging.getLogger()


# TODO: MetaData.clone()

# TODO: MetaPythonFunc() class

# TODO: MetaShellFunc() class


class MetaDataCacheMiss(Exception):
    pass


class MetaData(dict):

    def __init__(self):
        dict.__init__(self)
        MetaList(self, [], 'OVERRIDES')
        self._cache = {}

    def __setitem__(self, key, val):
        self.clean(key)
        dict.__setitem__(self, key, val)

    def __getitem__(self, key):
        var = dict.__getitem__(self, key)
        return var

    def eval(self, value):
        if isinstance(value, types.CodeType):
            value = eval(value, {}, self)
        if isinstance(value, MetaVar):
            value = value.get()
        return value

    def cache(self, var, value):
        self._cache[var] = value

    def get_cached(self, var):
        try:
            return self._cache[var]
        except KeyError:
            raise MetaDataCacheMiss(var)

    def clean(self, var):
        pass


class MetaVar(object):

    __slots__ = [ 'scope', 'name', 'value', 'override_if', ]

    def __new__(cls, scope, value=None, name=None):
        if isinstance(value, basestring):
            return super(MetaVar, cls).__new__(MetaString)
        elif isinstance(value, list):
            return super(MetaVar, cls).__new__(MetaList)
        elif isinstance(value, dict):
            return super(MetaVar, cls).__new__(MetaMap)
        elif isinstance(value, int):
            return super(MetaVar, cls).__new__(MetaInt)
        elif isinstance(value, bool):
            return super(MetaVar, cls).__new__(MetaBool)
        else:
            return super(MetaVar, cls).__new__(MetaString)

    def __init__(self, scope, value=None, name=None):
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
                return self.scope.get_cached(self.name)
            except MetaDataCacheMiss:
                pass
        value = self.scope.eval(self.value)
        if not isinstance(value, self.basetype):
            raise TypeError("invalid type %s in %r"%(type(value), self))
        if isinstance(self, MetaSequence):
            value = self.amend(value)
        if self.override_if:
            for override in self.scope['OVERRIDES']:
                if self.override_if.has_key(override):
                    value = self.override_if[override]
                    break
        # FIXME: implement prepend_if and append_if handling
        # if isinstance(self, MetaSequence):
        #     value = self.amend_if(value)
        if self.name is not None:
            self.scope.cache(self.name, value)
        return value


class MetaSequence(MetaVar):

    __slots__ = [ 'prepend', 'append', 'prepends', 'appends',
                  'prepend_if', 'append_if' ]

    def __init__(self, scope, value=None, name=None):
        self.prepends = []
        self.prepend_if = {}
        self.appends = []
        self.append_if = {}
        super(MetaSequence, self).__init__(scope, value, name)

    def __getitem__(self, index):
        return self.get().__getitem__(index)

    def __len__(self):
        return self.get().__len__()

    def __contains__(self, item):
        return self.get().__contains__(item)

    def index(self, sub, start=None, end=None):
        return self.get().index(sub, start, end)

    def count(self, sub, start=None, end=None):
        return self.get().count(sub, start, end)

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
        return MetaVar(self.scope, value)

    def set(self, value):
        super(MetaSequence, self).set(value)
        self.prepends = []
        self.appends = []


class MetaString(MetaSequence):

    __slots__ = []

    basetype = basestring

    def __str__(self):
        return self.get()

    def amend(self, value):
        if self.prepends:
            for amend_value in map(self.scope.eval, self.prepends):
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in map(self.scope.eval, self.appends):
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        return value

    @classmethod
    def eval(cls, value):
        # FIXME: do ${VARIABLE_NAME} style expansion here
        return value


class MetaList(MetaSequence):

    __slots__ = [ 'separator' ]

    basetype = list

    def __str__(self):
        return str(self.get())

    def __iter__(self):
        return self.get().__iter__()

    def __reversed__(self):
        return self.get().__reversed__()

    def split_str(self, value):
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
            for amend_value in map(self.scope.eval, self.prepends):
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                elif isinstance(amend_value, basestring):
                    value = self.split_str(amend_value) + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in map(self.scope.eval, self.appends):
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                elif isinstance(amend_value, basestring):
                    value += self.split_str(amend_value)
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
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
        return MetaVar(self.scope, value)


class MetaMap(MetaVar):

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

    def __init__(self, value=None):
        super(MetaBool, self).__init__(value, name)
        pass


class MetaInt(MetaVar):

    def __init__(self, value=None):
        super(MetaInt, self).__init__(value, name)
        pass


import unittest

class TestMetaVar(unittest.TestCase):

    def setUp(self):
        pass

    def test_init_default(self):
        d = MetaData()
        VAR = MetaVar(d)
        self.assertIsInstance(VAR, MetaString)

    def test_init_metavar(self):
        d = MetaData()
        FOO = MetaVar(d, '')
        BAR = MetaVar(d, FOO)
        self.assertIsInstance(BAR, MetaString)

    def test_init_string(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        self.assertIsInstance(VAR, MetaString)

    def test_init_list(self):
        d = MetaData()
        VAR = MetaVar(d, [42])
        self.assertIsInstance(VAR, MetaList)

    def test_set_get_string(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR.set('bar')
        self.assertEqual(VAR.get(), 'bar')

    def test_set_string_list(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        self.assertRaises(TypeError, VAR.set, (['bar']))

    def test_set_get_list(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.set(['bar'])
        self.assertEqual(VAR.get(), ['bar'])

    def test_set_list_string(self):
        d = MetaData()
        VAR = MetaVar(d, [])
        VAR.set(' foo bar ')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_set_list_bool(self):
        d = MetaData()
        VAR = MetaVar(d, [])
        self.assertRaises(TypeError, VAR.set, ({}))

    def test_prepend_string_1(self):
        d = MetaData()
        VAR = MetaVar(d, 'bar')
        VAR.prepend('foo')
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_string_2(self):
        d = MetaData()
        VAR = MetaVar(d, 'bar')
        VAR.prepend('foo')
        VAR.prepend('x')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_string_1(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR.append('bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_string_2(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR.append('bar')
        VAR.append('x')
        self.assertEqual(VAR.get(), 'foobarx')

    def test_prepend_list_1(self):
        d = MetaData()
        VAR = MetaVar(d, ['bar'])
        VAR.prepend(['foo'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_prepend_list_2(self):
        d = MetaData()
        VAR = MetaVar(d, ['bar'])
        VAR.prepend(['foo'])
        VAR.prepend(['x'])
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_list_1(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append(['bar'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_list_2(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append(['bar'])
        VAR.append(['x'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_3(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append(['bar', 'x', 'y'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x', 'y'])

    def test_append_list_string_1(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append('bar')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_list_string_2(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append('bar x')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_space(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append(' bar    x ')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_tab(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append('\tbar\tx\t')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_newline(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR.append('\nbar\nx\n')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_string_add_str(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR += 'bar'
        self.assertEqual(VAR.get(), 'foobar')

    def test_string_add_string(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR += MetaVar(d, 'bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_string_add_self(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR += VAR
        self.assertEqual(VAR.get(), 'foofoo')

    def test_string_add_3(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        ADDED = VAR + VAR + VAR
        self.assertEqual(ADDED.get(), 'foofoofoo')

    def test_string_add_3_mixed(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        ADDED = VAR + 'bar' + VAR
        self.assertEqual(ADDED.get(), 'foobarfoo')

    def test_list_add_str(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR += 'bar'
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_list_add_list_2(self):
        d = MetaData()
        VAR = MetaVar(d, ['foo'])
        VAR += ['bar', 'x']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_string_invalid_attribute(self):
        d = MetaData()
        VAR = MetaVar(d, '')
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_list_invalid_attribute(self):
        d = MetaData()
        VAR = MetaVar(d, [])
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_set_code(self):
        d = MetaData()
        VAR = MetaVar(d)
        VAR.set(compile('"foo" + "bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_code(self):
        d = MetaData()
        VAR = MetaVar(d, 'bar')
        VAR.prepend(compile('"foo"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_code(self):
        d = MetaData()
        VAR = MetaVar(d, 'foo')
        VAR.append(compile('"bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_set_code_with_metavars(self):
        d = MetaData()
        MetaVar(d, 'foo', 'FOO')
        MetaVar(d, 'bar', 'BAR')
        VAR = MetaVar(d)
        VAR.set(compile('FOO + " " + BAR', '<code>', 'eval'))
        value = VAR.get()
        self.assertEqual(value, 'foo bar')

    def test_string_iter(self):
        d = MetaData()
        VAR = MetaVar(d, 'foobar')
        value = ''
        for c in VAR:
            value += c
        self.assertEqual(value, 'foobar')

    def test_list_iter(self):
        d = MetaData()
        VAR = MetaVar(d, [1,2,3])
        sum = 0
        for i in VAR:
            sum += i
        self.assertEqual(sum, 6)

    def test_list_iter_reversed(self):
        d = MetaData()
        VAR = MetaVar(d, [1,2,3])
        value = None
        for i in reversed(VAR):
            if value is None:
                value = i
            else:
                value = value - i
        self.assertEqual(value, 0)

    def test_string_override_1(self):
        d = MetaData()
        VAR = MetaVar(d, 'bar')
        MetaVar(d, ['USE_foo'], 'OVERRIDES')
        VAR.override_if['USE_foo'] = 'foo'
        self.assertEqual(VAR.get(), 'foo')

    def test_string_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, '')
        MetaVar(d, ['USE_foo', 'USE_bar'], 'OVERRIDES')
        VAR.override_if['USE_foo'] = 'foo'
        VAR.override_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foo')

if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
# FIXME: use coverage analysis to check for untested code
