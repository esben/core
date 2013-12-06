import sys
import string
import re
import types
import copy

import logging
log = logging.getLogger()


# TODO: MetaData() class that derives from dict and includes eval cache, json
# dump, and more ...

# TODO: MetaData.clone()

# TODO: MetaPythonFunc() class

# TODO: MetaShellFunc() class

# FIXME: ensure that FOO.append(BAR) does immediate BAR.get(), as it would
# otherwise be difficult to implement MetaData.clone().

# TODO: extend MetaList so that MetaList.set('foo bar') will do the same as
# MetaList(['foo', 'bar'])


class MetaDataEval(object):

    def __init__(self):
        pass

    def clean(self, var):
        pass


class MetaData(dict):

    def __init__(self):
        self.eval = MetaDataEval()
        dict.__init__(self)

    def __setitem__(self, key, val):
        self.eval.clean(key)
        dict.__setitem__(self, key, val)

    def __getitem__(self, key):
        var = dict.__getitem__(self, key)
        return val


class MetaVar(object):

    __slots__ = [ 'scope', 'name', 'value', 'override_if', ]

    def __new__(cls, value=None, scope=None, name=None):
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

    def __init__(self, value=None, scope=None, name=None):
        if isinstance(value, MetaVar):
            value = value.get()
        if name is not None:
            self.scope[name] = self
        self.value = value
        assert not (name is not None and scope is None)
        assert scope is None or isinstance(scope, MetaData)
        self.scope = scope
        self.name = name
        self.override_if = {}

    def __repr__(self):
        return '%s(%r)'%(self.__class__.__name__, self.get())

    def __str__(self):
        return str(self.get())

    @classmethod
    def eval(cls, value):
        if isinstance(value, types.CodeType):
            value = eval(value)
        if isinstance(value, cls):
            value = value.get()
        return value

    def set(self, value):
        self.value = value

    def get(self, evaluate=True, override=True, amend=True):
        assert not ((amend or override) and not evaluate)
        assert not (override and not amend)
        value = self.value
        if evaluate:
            value = self.eval(value)
        if not isinstance(value, self.basetype):
            raise TypeError("invalid type %s in %r"%(type(value), self))
        if amend and isinstance(self, MetaSequence):
            value = self.amend(value)
        # FIXME: implement override_if
        # FIXME: implement prepend_if and append_if handling
        # if amend and isinstance(self, MetaSequence):
        #     value = self.amend_if(value)
        return value


class MetaSequence(MetaVar):

    __slots__ = [ 'prepend', 'append', 'prepends', 'appends',
                  'prepend_if', 'append_if' ]

    def __init__(self, value=None, scope=None, name=None):
        self.prepends = []
        self.prepend_if = {}
        self.appends = []
        self.append_if = {}
        super(MetaSequence, self).__init__(value, scope, name)

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

    def set(self, value):
        self.value = value
        self.prepends = []
        self.appends = []

    def prepend(self, value):
        self.prepends.append(value)

    def append(self, value):
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
        return MetaVar(value)

    def set(self, value):
        if isinstance(value, type(self)):
            value = value.get()
        if isinstance(value, types.CodeType):
            pass
        elif not isinstance(value, self.basetype):
            raise TypeError("cannot set %r object to %s value"%(
                    self, type(value)))
        self.value = value
        self.prepends = []
        self.appends = []


class MetaString(MetaSequence):

    __slots__ = []

    basetype = basestring

    def __str__(self):
        return self.get()

    def amend(self, value):
        if self.prepends:
            for amend_value in map(self.eval, self.prepends):
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in map(self.eval, self.appends):
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        return value

    @classmethod
    def eval(cls, value):
        value = super(MetaString, cls).eval(value)
        # FIXME: do ${VARIABLE_NAME} style expansion here
        return value


class MetaList(MetaSequence):

    __slots__ = [ 'ifs' ]

    basetype = list

    def __str__(self):
        return str(self.get())

    def __iter__(self):
        return self.get().__iter__()

    def __reversed__(self):
        return self.get().__reversed__()

    def amend(self, value):
        value = copy.copy(value)
        if self.prepends:
            for amend_value in map(self.eval, self.prepends):
                if isinstance(amend_value, self.basetype):
                    value = amend_value + value
                elif isinstance(amend_value, basestring):
                    ifs = getattr(self, 'ifs', ' \t\n')
                    value = re.split(
                        '[%s]+'%(ifs), string.strip(amend_value, ifs)) + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if self.appends:
            for amend_value in map(self.eval, self.appends):
                if isinstance(amend_value, self.basetype):
                    value += amend_value
                elif isinstance(amend_value, basestring):
                    ifs = getattr(self, 'ifs', ' \t\n')
                    value += re.split(
                        '[%s]+'%(ifs), string.strip(amend_value, ifs))
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
        return MetaVar(value)


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
        VAR = MetaVar()
        self.assertIsInstance(VAR, MetaString)

    def test_init_metavar(self):
        FOO = MetaVar('')
        BAR = MetaVar(FOO)
        self.assertIsInstance(BAR, MetaString)

    def test_init_string(self):
        VAR = MetaVar('foo')
        self.assertIsInstance(VAR, MetaString)

    def test_init_list(self):
        VAR = MetaVar([42])
        self.assertIsInstance(VAR, MetaList)

    def test_set_get_string(self):
        VAR = MetaVar('foo')
        VAR.set('bar')
        self.assertEqual(VAR.get(), 'bar')

    def test_set_string_list(self):
        VAR = MetaVar('foo')
        self.assertRaises(TypeError, VAR.set, (['bar']))

    def test_set_get_list(self):
        VAR = MetaVar(['foo'])
        VAR.set(['bar'])
        self.assertEqual(VAR.get(), ['bar'])

    def test_set_list_string(self):
        VAR = MetaVar(['foo'])
        self.assertRaises(TypeError, VAR.set, ('bar'))

    def test_prepend_string_1(self):
        VAR = MetaVar('bar')
        VAR.prepend('foo')
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_string_2(self):
        VAR = MetaVar('bar')
        VAR.prepend('foo')
        VAR.prepend('x')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_string_1(self):
        VAR = MetaVar('foo')
        VAR.append('bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_string_2(self):
        VAR = MetaVar('foo')
        VAR.append('bar')
        VAR.append('x')
        self.assertEqual(VAR.get(), 'foobarx')

    def test_prepend_list_1(self):
        VAR = MetaVar(['bar'])
        VAR.prepend(['foo'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_prepend_list_2(self):
        VAR = MetaVar(['bar'])
        VAR.prepend(['foo'])
        VAR.prepend(['x'])
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_list_1(self):
        VAR = MetaVar(['foo'])
        VAR.append(['bar'])
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_list_2(self):
        VAR = MetaVar(['foo'])
        VAR.append(['bar'])
        VAR.append(['x'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_3(self):
        VAR = MetaVar(['foo'])
        VAR.append(['bar', 'x', 'y'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x', 'y'])

    def test_append_list_string_1(self):
        VAR = MetaVar(['foo'])
        VAR.append('bar')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_list_string_2(self):
        VAR = MetaVar(['foo'])
        VAR.append('bar x')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_space(self):
        VAR = MetaVar(['foo'])
        VAR.append(' bar    x ')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_tab(self):
        VAR = MetaVar(['foo'])
        VAR.append('\tbar\tx\t')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_list_string_2_newline(self):
        VAR = MetaVar(['foo'])
        VAR.append('\nbar\nx\n')
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_string_add_str(self):
        VAR = MetaVar('foo')
        VAR += 'bar'
        self.assertEqual(VAR.get(), 'foobar')

    def test_string_add_string(self):
        VAR = MetaVar('foo')
        VAR += MetaVar('bar')
        self.assertEqual(VAR.get(), 'foobar')

    def test_string_add_self(self):
        VAR = MetaVar('foo')
        VAR += VAR
        self.assertEqual(VAR.get(), 'foofoo')

    def test_string_add_3(self):
        VAR = MetaVar('foo')
        ADDED = VAR + VAR + VAR
        self.assertEqual(ADDED.get(), 'foofoofoo')

    def test_string_add_3_mixed(self):
        VAR = MetaVar('foo')
        ADDED = VAR + 'bar' + VAR
        self.assertEqual(ADDED.get(), 'foobarfoo')

    def test_list_add_str(self):
        VAR = MetaVar(['foo'])
        VAR += 'bar'
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_list_add_list_2(self):
        VAR = MetaVar(['foo'])
        VAR += ['bar', 'x']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_string_invalid_attribute(self):
        VAR = MetaVar('')
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_list_invalid_attribute(self):
        VAR = MetaVar([])
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_set_code(self):
        VAR = MetaVar()
        VAR.set(compile('"foo" + "bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_code(self):
        VAR = MetaVar('bar')
        VAR.prepend(compile('"foo"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_code(self):
        VAR = MetaVar('foo')
        VAR.append(compile('"bar"', '<code>', 'eval'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_set_code_with_metavars(self):
        global FOO, BAR
        FOO = MetaVar('foo')
        BAR = MetaVar('bar')
        VAR = MetaVar()
        VAR.set(compile('FOO + " " + BAR', '<code>', 'eval'))
        value = VAR.get()
        del FOO, BAR
        self.assertEqual(value, 'foo bar')

    def test_string_iter(self):
        VAR = MetaVar('foobar')
        value = ''
        for c in VAR:
            value += c
        self.assertEqual(value, 'foobar')

    def test_list_iter(self):
        VAR = MetaVar([1,2,3])
        sum = 0
        for i in VAR:
            sum += i
        self.assertEqual(sum, 6)

    def test_list_iter_reversed(self):
        VAR = MetaVar([1,2,3])
        value = None
        for i in reversed(VAR):
            if value is None:
                value = i
            else:
                value = value - i
        self.assertEqual(value, 0)

if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
# FIXME: use coverage analysis to check for untested code
