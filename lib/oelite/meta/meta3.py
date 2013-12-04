import sys
import string
import re
import types

import logging
log = logging.getLogger()


class MetaVariable(object):


    # FIXME: __slots__ = [ 'value', 'prepend', 'append', 'override_if',
    # 'prepend_if', 'append_if', 'ifs', ... ]

    def __init__(self, name, value=None):
        self.__name__ = name
        self.value = value
        self.prepends = []
        self.appends = []
        #if value is not None:
        #    self.type = type(value)
        #else:
        #    self.type = None
        self.override_if = {}
        self.prepend_if = {}
        self.append_if = {}


    def __repr__(self):
        return '%s(%s)'%(self.__class__.__name__, self.__name__)

    def __str__(self):
        return str(self.get())


    def __setitem__(self, key, value): # required by MutableMapping
        assert isinstance(self.value, dict)
        self.value[key] = value

    def __delitem__(self, key): # required by MutableMapping
        assert isinstance(self.value, dict)
        del self.value[key]

    def __getitem__(self, key): # required by Mapping
        assert isinstance(self.value, dict)
        return self.value[key] # FIXME: need to do something with the value
                               # returned, ie. eval/expansion...  Better
                               # return the evaluated/expanded value here, and
                               # provide custom access functions for getting
                               # raw values for those special situation where
                               # that might be needed.

    def __contains__(self, item): # required by Container
        # FIXME: not implemented
        pass


    def __eval__(self, value):
        print '__eval__', value
        if isinstance(value, types.CodeType):
            value = eval(value)
        if isinstance(value, MetaVariable):
            value = value.get()
        return value


    def set(self, value):
        self.value = value
        self.prepends = []
        self.appends = []

    def prepend(self, value):
        self.prepends.append(value)

    def append(self, value):
        self.appends.append(value)


    def get(self, evaluate=True, override=True, amend=True):
        assert not ((amend or override) and not evaluate)
        value = self.value
        if evaluate:
            value = self.__eval__(value)
        if amend and self.prepends:
            if not type(value) in (str, list):
                raise TypeError(
                    "prepend to %s not supported: %r"%(type(value), self))
            for amend_value in map(self.__eval__, self.prepends):
                if type(value) == type(amend_value):
                    value = amend_value + value
                elif (isinstance(value, list) and
                      isinstance(amend_value, str)):
                    ifs = getattr(self, 'ifs', ' \t\n')
                    value = re.split(
                        '[%s]+'%(ifs), string.strip(amend_value, ifs)) + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if amend and self.appends:
            if not type(value) in (str, list):
                raise TypeError(
                    "append to %s not supported: %r"%(type(value), self))
            for amend_value in map(self.__eval__, self.appends):
                if type(value) == type(amend_value):
                    value += amend_value
                elif (isinstance(value, list) and
                      isinstance(amend_value, str)):
                    ifs = getattr(self, 'ifs', ' \t\n')
                    value += re.split(
                        '[%s]+'%(ifs), string.strip(amend_value, ifs))
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        # FIXME: implement override_if, prepend_if, append_if handling
        return value


    def __add__(self, other):
        value = self.get()
        if isinstance(other, MetaVariable):
            other = other.get()
        # FIXME: return an annonymous MetaVariable instead of value
        return value + other


if __name__ == "__main__":
    logging.basicConfig()
    FOO = MetaVariable('FOO')
    FOO.set('foo')
    FOO.prepend('x')
    FOO.prepend('y')
    FOO.append('1')
    FOO.append('2')
    print '%r = %r'%(FOO, FOO.get())
    BAR = MetaVariable('BAR')
    BAR.set(['foo'])
    BAR.append(' hello    world ')
    BAR.append(compile('"foo" + "bar"', '<unknown1>', 'eval'))
    BAR.append(['and', 'some', 'more'])
    print '%r = %r'%(BAR, BAR.get())
    FOOBAR = MetaVariable('FOOBAR')
    FOOBAR.set(compile('"foo" + "bar" + str(FOO)', '<unknown2>', 'eval'))
    FOOBAR.prepend(compile('FOO + str(BAR) + FOO', '<unknown3>', 'eval'))
    print '%r = %r'%(FOOBAR, FOOBAR.get())
    sys.exit(0)
