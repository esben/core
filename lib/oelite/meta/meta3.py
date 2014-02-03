from __future__ import print_function

import sys
import string
import re
import types
import collections
import copy
import json

import logging
log = logging.getLogger()


# TODO: implement dynvar handling, for correct signature generation without
# disturbance for changing DATE, TIME, MANIFEST_ORIGIN and so on.

# TODO: Implement handling of PythonExpression.cacheable, so that
# PythonExpression variables can be allowed to be cached or required to be
# kept uncacheable. Any variable that depends on one or more uncacheable
# expressions also become uncacheable.

# TODO: Ensure that lists set or added to MetaList are copied, so that they
# cannot be changed through other references, and thus circumventing the
# cache.  Same for Addition of MetaList or any other container types.

# TODO: Figure out if MetaDict and MetaDataCache is 100% safely designed,
# ie. is it possible to change cached MetaDict without invalidating the cache?


# TODO: Add method to MetaData to check if a specific variable (fx. MACHINE)
# is referenced by any (other) variable.  To do this, any variables not
# already cached needs to be dummy .get()'ed and then the cache be checked for
# any references to the variable.
#
# This method should be used for setting EXTRA_ARCH if MACHINE is referenced.
# For recipe types where MACHINE is not allowed, MACHINE should be cleaned out
# soon after recipe type is "forked".

# TODO: add MetaList.remove() and MetaList.remove_if() functions.  The removes
# should be applied in amend, after applying prepends and appends, and similar
# for *_if.  Removal of non-existant value should not cause any error, but
# just silently ignored (which is different from list.remove()).

# TODO: Add support for explicit exclusion of selected variables from
# expansion. This should be preferred in favour of legacy partial expansion,
# and perhaps even fully replace it, as it is more predictable, and allows
# proper error handling of missing variables that actually were meant to be
# defined as well as avoiding replacing variables that were really meant to be
# left in unexpanded.

# TODO: MetaInt

# TODO: MetaPythonFunc() class.  See also old MetaData.pythonfunc_init(),
# MetaData.get_pythonfunc_globals(), MetaData.get_pythonfuncs(),
# MetaData.get_pythonfunc(), MetaData.get_pythonfunc_code().

# TODO: MetaShellFunc() class

# TODO: include task (True/False) slot/attribute in python and shell func
# classes

# TODO: figure out a safe way to use PythonExpression in MetaDict keys, or add
# proper error handling on attempts to do so.

# USE flag design.
#
# USE flags are found in the USE MetaDict.
#     USE['nls'] = False
# Unset USE flags are None
#     USE['nls'] = None
# But for boolean USE flags, both False and None means the flag is unset, and
# True that the flag is set.
#
# Recipes metadata marks a variable as a USE flag, fx.
#     useflag nls bool
# which should map to something like
#     USE['nls'] = MetaBool(d, value=None)
#     DEFAULT_USE['nls'] = True
# Further customization of the default values can be done by direct access to
# the DEFAULT_USE variable.
#
# USE flag domains are defined by USE_DOMAINS
#     USE_DOMAINS = [ 'LOCAL', 'MACHINE', 'DISTRO', 'DEFAULT' ]
# When a use flag is set, fx. in a distro config file, the particular domain
# must be activated.
#     use DISTRO

#     USE['nls'] = False
# should map to setting
#     DISTRO_USE['nls'] = False
# This way, copy-pase from fx. distro config to machine config, will do the
# right thing, instead of either using wrong domain or giving a parse error.
# The use flag domain is only activated as long as the file it was activated
# in is being parsed.
#
# To force/set a recipe specific value for a use flag, simply do
#     USE['nls'] = True
#
# When post processing the recipe metadata, a hook must loop over all the USE
# variable keys.  For each key, if the value is None, search through the
# USE_DOMAINS defined, stopping on first matching key.  So if a domain has the
# key, and value is None, the USE flag is unset.

# TODO: figure out required life-cycle model...  do we need to have
# pickle/unpickle for parallel parse?
#
# Metadata from bakery.conf -> oe-lite.conf -> core.oeclass
# is always parsed.
#
# A signature of resulting "raw" base metadata is needed to decide if all
# recipes needs to be reparsed, or only those that has changed input file
# mtimes.  This signature is added to the raw metadata.
#
# This raw base metadata signature should not care about dynvars, ie. all
# variables are just taken "as is" (this implies that DATE, TIME, DATETIME
# variables are not set at this point, but much later, so that it is always
# set, even when re-using cached recipe metadata).  This makes it easier to
# handle changes to manifest origin and other dynvars, requring full reparse
# when they are changed.
#
# Setting of DATETIME variable should be moved to datetime.oeclass file, and
# explicitly inherited only by those classes/recipes that really need it.
# This class should setup a hook to set DATE, TIME and DATETIME to common
# values for all recipes, but after caching is resolved, so that all recipes
# get the same values, no matter if they were reparsed or read from cache.
#
# Signature of imported environment variables must also be included in this
# raw base metadata and thus the signature of it.
#
# As needed, the recipes are parsed, each recipe in a separate process.  The
# metadata does therefore not need to be copied.  When done, a signature of
# the resulting recipe metadata is calculated and inserted into the recipe
# metadata.  The recipe metadata is then serialized into a disk file,
# preferably JSON format or other human readable format for easier debugging.
# If needed (hopefully not, but likely), a special summary of the recipe
# metadata must be written to a separate file, including all the information
# needed to create the cookbook.
#
# Back in the main process, the recipe metadata (or just the summary, if it is
# implemented) is read in for all recipes, and used to create the cookbook.
#
# After the runq is created from the cookbook, all tasks included in the build
# are read in from cache (JSON) files, if recipe metadata signature (or token)
# in the file is identical to the recipe metadata.  If cache is invalid, a
# process is created for each task, and this process finalizes the task
# metadata (flattening it to FlatMetaData, collapsing all appends, prepends,
# updates, override_if, and so on, removing all unneeded variables (according
# to .emit and .omit attributes and such).  The signature of the resulting
# FlatMetaData is calculated, and this is written to a cache file (JSON)
# together with the task metadata.
#
# For improved debugging support, it would be nice if each variable could be
# given a signature, so that we can pinpoints exactly what has changed to
# cause a task to be rebuilt.
#

# TODO: When a mtime difference for a recipe is detected, the recipe metadata
# will be reparsed.  Back in the baker process, the (re)parsed metdata is
# compared to the previous metadata (if available, loading it from old cache
# file), and based on metadata signature being changed, decide if the old
# (task) cache can still be used, or if we have to regenerate that.
#
# Also, when metadata is different, add a manifest command for telling which
# variables have changed in a specific recipe (or task?) metadata since last
# time.  Optionally, allowing to specify a specific metadata dump dir.  Add a
# manifest command for generating a new metadata dump/cache dir for later
# comparision.
#

# TODO: test if builtin filter() can be used for efficient retrieving list of
# variables with a specific attribute set (True).

# TODO: Reimplement MetaData.import_env as method in some other module, as it
# is not logically part of the MetaData abstraction.

# TODO: add_hook() method

# TODO: Add API and internal documentation to all classes, attributes and
# methods!


import hashlib
import pprint

class MetaHasher(object):

    def __init__(self):
        self.reset()

    def reset(self):
        self.m = hashlib.md5()

    def update_raw(self, value):
        #print(value, end='')
        self.m.update(value)

    def update(self, value):
        if isinstance(value, dict):
            self.update_raw(pprint.pformat(self.hash_repr(value)))
        else:
            self.update_raw(repr(self.hash_repr(value)))

    @staticmethod
    def hash_repr(value):
        if isinstance(value, unicode):
            return value.encode('utf-8')
        elif type(value) == dict:
            return dict(map(lambda (k, v): (
                        (str(k) if isinstance(k, unicode) else k),v),
                            value.items()))
        elif type(value) in (int, float, str, dict, list,
                             PythonExpression):
            return value
        elif isinstance(value, MetaVar):
            return value.signature()
        else:
            raise TypeError("cannot hash %s value: %s"%(
                    type(value).__name__, value))

    def __repr__(self):
        return "s'%s'"%(self.m.hexdigest())

    def __str__(self):
        return self.m.hexdigest()

    def __eq__(self, other):
        if isinstance(other, MetaHasher):
            return self.m.digest() == other.m.digest()
        elif isinstance(other, basestring):
            return self.m.hexdigest() == other
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


def all_slots(cls):
    slots = set(getattr(cls, '__slots__', []))
    for base in cls.__bases__:
        slots.update(all_slots(base))
    return slots


def hash_slots(cls):
    slots = set(getattr(cls, '__slots__', [])).difference(
        getattr(cls, 'nohash_slots', []))
    for base in cls.__bases__:
        slots.update(hash_slots(base))
    return slots


class MetaDataRecursiveEval(Exception):
    pass

class MetaDataDuplicateDictKey(Exception):
    pass


class MetaDataStack(object):

    __slots__ = [ 'var', 'deps', 'scope' ]

    def __init__(self, scope):
        self.scope = scope
        self.var = []
        self.deps = []

    # self.var[-1] is the currently-being-evaluated variable

    # self.deps[-1] is list of variables that the currently-being-evaluated
    # variable depends on.  If variable is a string, the variable is
    # undefined, and should be registered with MetaData.watchers.

    def __str__(self, prefix='\n  '):
        return prefix.join(self.var)

    def push(self, var):
        assert isinstance(var, MetaVar)
        if var in self.var:
            raise MetaDataRecursiveEval(
                '%s->%s'%('->'.join(map(lambda v: v.name, self.var)), var.name))
        self.var.append(var)
        self.deps.append(set())

    def pop(self):
        var = self.var.pop()
        deps = self.deps.pop()
        if self.var:
            self.deps[-1].add(var)
            self.deps[-1].update(deps)
        return deps

    def add_dep(self, var):
        if not self.deps:
            return
        if isinstance(var, basestring):
            try:
                var = self.scope[var]
            except KeyError:
                pass
        self.deps[-1].add(var)

    def add_deps(self, deps):
        if self.deps and deps:
            self.deps[-1].update(deps)

    def clear_deps(self):
        self.deps[-1] = set()


class MetaData(dict):

    __slots__ = [ 'stack', 'watchers' ]

    def __init__(self, init=None):
        dict.__init__(self)
        self.watchers = {}
        if init is None:
            self.stack = MetaDataStack(self)
            MetaList(self, 'OVERRIDES', [])
        elif isinstance(init, MetaData):
            for name,var in init.iteritems():
                var.copy(self)
            self.stack = MetaDataStack(self)
        elif isinstance(init, dict):
            self.stack = MetaDataStack(self)
            for name,var in init.iteritems():
                MetaVar(self, name, var)
            if not 'OVERRIDES' in self:
                MetaList(self, 'OVERRIDES', [])

    def __setitem__(self, key, val):
        # FIXME: remove this assert when/if dot notation is droppped
        assert not '.' in key
        if self.__contains__(key):
            self[key].set(val)
            return
        if type(val) in (str, unicode, list, dict, int, long, bool):
            MetaVar(self, key, val)
        elif not isinstance(val, MetaVar):
            raise TypeError('cannot assign %s to MetaData'%(type(val)))
        else:
            val.name = key
            dict.__setitem__(self, key, val)
        # Invalidate any variables with watchers on this variable (name),
        # ie. variables that have cached values depending on the non-existance
        # of this variable.
        for var in list(self.watchers.get(key, [])):
            var.cache_invalidate()

    def __getitem__(self, key):
        var = dict.__getitem__(self, key)
        return var

    def __delitem__(self, key):
        var = dict.__getitem__(self, key)
        var.cache_invalidate()
        var.name = None
        dict.__delitem__(self, key)

    def expand_full(self, value):
        if not isinstance(value, basestring):
            return value
        def expand(sub):
            sub = sub.group(0)
            name = sub[2:-1]
            var = dict.__getitem__(self, name)
            value = var.get()
            if not isinstance(value, basestring):
                raise TypeError(
                    "expanded variables must be string: %s is %s"%(
                        name, type(value)))
            return value
        return re.sub(self.expand_re, expand, value)

    def expand_partial(self, value):
        # FIXME: add support for partial expand of MetaDict values
        #if not isinstance(value, basestring):
        #    return value
        def expand(sub):
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
        return re.sub(self.expand_re, expand, value)

    def expand_clean(self, value):
        # FIXME: add support for clean expand of MetaDict values
        #if not isinstance(value, basestring):
        #    return value
        def expand(sub):
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
        return re.sub(self.expand_re, expand, value)

    expand_re = re.compile(r'\$\{[a-zA-Z_]+\}')
    def expand(self, value, method='full'):
        if method == 'no':
            return value
        elif method == 'full':
            expand = self.expand_full
        elif method == 'partial':
            expand = self.expand_partial
        elif method == 'clean':
            expand = self.expand_clean
        else:
            raise TypeError('invalid expand method: %r'%(method))
        if isinstance(value, basestring):
            return expand(value)
        elif isinstance(value, list):
            return map(expand, value)
        else:
            return value

    def eval(self, value):
        if isinstance(value, PythonExpression):
            value = eval(value.code, {}, self)
        if isinstance(value, MetaVar):
            value = value.get()
        if isinstance(value, dict):
            expanded = {}
            for key, val in value.iteritems():
                key = self.expand(self.eval(key))
                if key in expanded:
                    raise MetaDataDuplicateDictKey(key)
                expanded[key] = self.expand(self.eval(val))
            value = expanded
        return value

    def __repr__(self):
        return "%s()"%(self.__class__.__name__)

    def flattened(self):
        d = {}
        for name, var in self.iteritems():
            if name == 'OVERRIDES':
                continue
            d[name] = var.get()
        return d

    def is_solitary(self, var):
        if isinstance(var, basestring):
            return self.is_solitary(self[var])
        assert isinstance(var.name, basestring) and not '.' in var
        assert var.scope == self
        self.cache_all()
        for other in self.values():
            if other == var:
                continue
            #if other.cache and var in other.cache[1]:
            if var in other.cache[1]:
                return False
        try:
            watchers = self.watchers[var.name]
        except KeyError:
            pass
        else:
            if watchers:
                return False
        return True

    def cache_all(self):
        for name, var in self.iteritems():
            if not var.cache:
                var.get()

    def __eq__(self, other):
        if isinstance(other, MetaData):
            return self.signature() == other.signature()
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def signature(self, t=str, dynvars=[]):
        if t == str:
            m = hashlib.md5()
            for name,var in sorted(self.iteritems(), key=lambda x: x[0]):
                # FIXME: skip if name is in dynvars
                m.update('%s:%s\n'%(name, var.signature(dynvars=dynvars)))
            m = m.hexdigest()
        elif t == dict:
            m = {}
            for name,var in self.iteritems():
                m[str(name)] = var.signature(dynvars=dynvars)
        else:
            raise TypeError("invalid type argument t: %s"%(t))
        return m

    def dumps(self, *args, **kwargs):
        obj = {
            '__jsonclass__': [self.__class__.__name__],
            'dict': dict(self),
        }
        kwargs['default'] = MetaVar.json_encode
        return json.dumps(obj, *args, **kwargs)

    @staticmethod
    def loads(s, *args, **kwargs):
        d = MetaData()
        kwargs['object_hook'] = d.json_decode
        return json.loads(s, *args, **kwargs)

    def json_decode(self, obj):
        try:
            cls = obj.pop('__jsonclass__')
        except KeyError:
            return obj
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
            instance_name = name = obj.pop('name')
            instance = constructor(self, name, *args, **kwargs)
        elif issubclass(constructor, MetaData):
            # Update (replace) the MetaData dict with the decoded variables
            assert len(self) == len(obj['dict'])
            dict.update(self, obj['dict'])
            assert len(self) == len(obj['dict'])
            del obj['dict']
            instance = self
        else:
            instance = constructor(*args, **kwargs)
        for name, value in obj.iteritems():
            setattr(instance, name, value)
        return instance

    def print(self, details=False, sep=None, file=sys.stdout):
        if sep is None:
            sep = '\n' if details else ''
        names = sorted(self.keys())
        while names:
            name = names.pop()
            var = self[name]
            value = repr(var.get())
            if details:
                source = var.get(evaluate=False)
                if source != value:
                    file.write("# %s = %s\n"%(name, source))
            file.write("%s = %s%s\n"%(name, value, sep if names else ''))


class MetaVar(object):

    __slots__ = [ 'scope', 'name', 'value', 'override_if', 'emit', 'omit',
                  'cache', 'watchers' ]
    nohash_slots = [ 'scope', 'cache', 'watchers' ]

    fixup_types = []

    def __new__(cls, scope, name=None, value=None):
        if cls != MetaVar:
            return super(MetaVar, cls).__new__(cls)
        if isinstance(value, MetaVar):
            return super(MetaVar, cls).__new__(type(value))
        elif isinstance(value, basestring):
            return super(MetaVar, cls).__new__(MetaString)
        elif isinstance(value, list):
            return super(MetaVar, cls).__new__(MetaList)
        elif isinstance(value, dict):
            return super(MetaVar, cls).__new__(MetaDict)
        elif isinstance(value, bool):
            return super(MetaVar, cls).__new__(MetaBool)
        elif isinstance(value, int):
            return super(MetaVar, cls).__new__(MetaInt)
        else:
            return super(MetaVar, cls).__new__(MetaString)

    def __init__(self, scope, name=None, value=None):
        assert isinstance(scope, MetaData)
        assert (value is None or
                isinstance(value, self.basetype) or
                isinstance(value, type(self)) or
                isinstance(value, PythonExpression))
        self.scope = scope
        self.cache = None
        self.watchers = set()
        if isinstance(value, MetaVar):
            self.scope = scope
            for attr in all_slots(self.__class__):
                if attr in ('scope', 'name', 'cache', 'watchers'):
                    continue
                try:
                    attr_val = getattr(value, attr)
                    if isinstance(attr_val, OverrideDict):
                        attr_val = attr_val.copy()
                        attr_val.var = self
                    elif isinstance(attr_val, collections.Container):
                        attr_val = copy.deepcopy(attr_val)
                    setattr(self, attr, attr_val)
                except AttributeError:
                    pass
        else:
            self.value = value
        self.name = name
        self.override_if = OverrideDict()
        if name is not None and not '.' in name:
            self.scope[name] = self

    def copy(self, scope=None):
        if scope is None:
            return self.__class__(self.scope, None, self)
        else:
            return self.__class__(scope, self.name, self)

    def __setattr__(self, name, value):
        if name in ('override_if', 'prepend_if', 'append_if', 'update_if'):
            value.var = self
        object.__setattr__(self, name, value)

    def __str__(self):
        return str(self.get())

    def set(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        if not (isinstance(value, self.basetype) or
                self.is_fixup_type(value) or
                value is None or
                isinstance(value, PythonExpression)):
            raise TypeError("cannot set %r to %s value"%(
                    self, type(value).__name__))
        self.cache_invalidate()
        self.value = value

    def weak_set(self, value):
        if self.value is None:
            self.cache_invalidate()
            return self.set(value)

    def is_fixup_type(self, value):
        for fixup_type in self.fixup_types:
            if isinstance(value, fixup_type):
                return True
        return False

    # Format of MetaVar.cache attribute: (value, deps)

    def get(self, evaluate=True):
        assert isinstance(evaluate, bool)
        if evaluate:
            try:
                value = self.cache[0]
            except:
                self.scope.stack.push(self)
            else:
                self.scope.stack.add_dep(self)
                self.scope.stack.add_deps(self.cache[1])
                return value
        try:
            if evaluate:
                value = self.scope.eval(self.value)
                if self.is_fixup_type(value):
                    value = self.fixup(value)
                if not (isinstance(value, self.basetype) or
                        value is None):
                    raise TypeError("invalid type in %s %s value: %s"%(
                            type(self).__name__, self.name,
                            type(value).__name__))
            else:
                if self.value is None:
                    value = []
                else:
                    value = [self.value]
            if isinstance(self, MetaSequence):
                value = self.amend(value, evaluate)
            if self.override_if:
                for override in self.scope['OVERRIDES']:
                    if override in self.override_if:
                        if evaluate:
                            self.scope.stack.clear_deps()
                            value = self.scope.eval(self.override_if[override])
                            if not (isinstance(value, self.basetype) or
                                    value is None):
                                raise TypeError(
                                    "invalid type in %s %s override: %s"%(
                                        type(self).__name__, self.name,
                                        type(value).__name__))
                        else:
                            if self.override_if[override] is None:
                                value = []
                            else:
                                value = [self.override_if[override]]
                        break
                if evaluate:
                    self.scope.stack.add_dep('OVERRIDES')
            if isinstance(self, MetaSequence):
                value = self.amend_if(value, evaluate)
            if isinstance(value, basestring) and evaluate:
                value = self.scope.expand(value, method=self.expand)
            if evaluate:
                self.cache_value(value)
        finally:
            if evaluate:
                self.scope.stack.pop()
        if not evaluate:
            if not value:
                return None
            value = filter(lambda v: False if v is None else True, value)
            value = map(
                lambda v: str(v) if isinstance(v, PythonExpression)
                else repr(v), value)
            value = ' + '.join(value)
        return value

    def cache_value(self, value):
        self.cache = (value, self.scope.stack.deps[-1])
        for var in self.cache[1]:
            if isinstance(var, MetaVar):
                var.watchers.add(self)
            else:
                assert isinstance(var, basestring)
                if var in self.scope.watchers:
                    self.scope.watchers[var].add(self)
                else:
                    self.scope.watchers[var] = set([self])

    def cache_invalidate(self, recurse=True):
        # Loop over list of variables that depends on this variable (this list
        # is updated by the variables that depend on this variable as they are
        # storing their own cached value), and invalidate their cache
        # information.
        if recurse:
            for var in list(self.watchers):
                var.cache_invalidate(recurse=False)
        # Clear any watchers information registered by this variable
        if not self.cache:
            return
        for var in self.cache[1]:
            if isinstance(var, basestring):
                self.scope.watchers[var].remove(self)
            else:
                var.watchers.remove(self)
        # And clear the cached value and it's dependency information
        self.cache = None

    def signature(self, m=None, dynvars=[]):
        if m is None:
            m = MetaHasher()
        m.update_raw(self.__class__.__name__ + '\n')
        for slot in sorted(hash_slots(self.__class__)):
            value = getattr(self, slot, None)
            if value is None:
                continue
            if isinstance(value, OverrideDict) and not value:
                continue
            # FIXME: skip empty appends/prepends if it improves performance
            m.update_raw(slot + ':')
            if isinstance(value, list):
                m.update(map(m.hash_repr, value))
            elif isinstance(value, dict):
                m.update(dict(map(lambda e: (e[0], m.hash_repr(e[1])),
                                  value.iteritems())))
            else:
                m.update(value)
            m.update_raw('\n')
        return m

    @staticmethod
    def json_encode(var):
        assert isinstance(var, MetaVar)
        return var.json_obj()

    def json_obj(self):
        import inspect
        slots = set()
        for cls in inspect.getmro(self.__class__):
            try:
                slots.update(cls.__slots__)
            except AttributeError:
                pass
        obj = { '__jsonclass__': [self.__class__.__name__] }
        for slot in slots:
            if slot == 'scope':
                continue
            try:
                attr = getattr(self, slot)
                if isinstance(attr, OverrideDict):
                    obj[slot] = attr.json_obj()
                elif type(attr) in (str, unicode, int, long, float, bool,
                                    types.NoneType, list, dict):
                    obj[slot] = attr
            except AttributeError:
                pass
        return obj


class OverrideDict(dict):

    __slots__ = [ 'dict', 'var' ]

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    def __setitem__(self, key, value):
        if isinstance(value, MetaVar):
            value = value.get()
        if not (value is None or
                isinstance(value, self.var.basetype) or
                isinstance(value, PythonExpression) or
                self.var.is_fixup_type(value)):
            raise TypeError("cannot set %r override to %s value"%(
                    self.var.name or type(self.var).__name__,
                    type(value).__name__))
        self.var.cache_invalidate()
        dict.__setitem__(self, key, value)

    def json_obj(self):
        return { '__jsonclass__': [self.__class__.__name__, [self]] }


class MetaSequence(MetaVar):

    __slots__ = [ 'prepends', 'appends',
                  'prepend_if', 'append_if' ]

    def __init__(self, scope, name=None, value=None):
        if isinstance(value, MetaVar):
            for attr in MetaSequence.__slots__:
                setattr(self, attr, getattr(value, attr))
        else:
            self.prepends = []
            self.prepend_if = OverrideDict()
            self.appends = []
            self.append_if = OverrideDict()
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
        if not (isinstance(value, self.basetype) or
                self.is_fixup_type(value) or
                value is None or
                isinstance(value, PythonExpression)):
            raise TypeError('cannot prepend %s to %s'%(type(value), type(self)))
        self.cache_invalidate()
        self.prepends.append(value)

    def append(self, value):
        if isinstance(value, MetaVar):
            value = value.get()
        if not (isinstance(value, self.basetype) or
                self.is_fixup_type(value) or
                value is None or
                isinstance(value, PythonExpression)):
            raise TypeError('cannot append %s to %s'%(type(value), type(self)))
        self.cache_invalidate()
        self.appends.append(value)

    def __add__(self, other):
        if not (isinstance(other, type(self)) or
                  isinstance(other, self.basetype)):
            raise TypeError(
                "cannot concatenate %s and %s objects"%(
                    type(self), type(other)))
        #value = self.__class__(self.scope)
        #self.scope.stack.push(value)
        #value.set(self.get())
        #if isinstance(other, MetaVar):
        #    other = other.get()
        #if other:
        #    value.append(other)
        #self.scope.stack.pop()
        #return value
        value = self.copy()
        self.scope.stack.push(value)
        self.scope.stack.add_dep(self)
        if isinstance(other, MetaVar):
            self.scope.stack.add_dep(other)
        value.append(other)
        self.scope.stack.pop()
        return value

    def set(self, value):
        super(MetaSequence, self).set(value)
        self.prepends = []
        self.appends = []

    def weak_set(self, value):
        if self.value is None and not self.prepends and not self.appends:
            self.cache_invalidate()
            return self.set(value)

    def amend_prepend(self, value, amend_value, evaluate):
        if evaluate:
            amend_value = self.scope.eval(amend_value)
        if amend_value is None:
            return value
        if value is None:
            value = self.empty
        if evaluate:
            if isinstance(amend_value, self.basetype):
                value = amend_value + value
            elif self.is_fixup_type(amend_value):
                value = self.fixup(amend_value) + value
            else:
                raise TypeError(
                    "unsupported prepend operation: %s to %s"%(
                        type(amend_value), type(value)))
        else:
            value = [amend_value] + value
        return value

    def amend_append(self, value, amend_value, evaluate):
        if evaluate:
            amend_value = self.scope.eval(amend_value)
        if amend_value is None:
            return value
        if value is None:
            value = self.empty
        if evaluate:
            if isinstance(amend_value, self.basetype):
                value = value + amend_value
            elif self.is_fixup_type(amend_value):
                value = value + self.fixup(amend_value)
            else:
                raise TypeError(
                    "unsupported append operation: %s to %s"%(
                        type(amend_value), type(value)))
        else:
            value = value + [amend_value]
        return value

    def amend(self, value, evaluate):
        if self.prepends:
            for amend_value in self.prepends:
                value = self.amend_prepend(value, amend_value, evaluate)
        if self.appends:
            for amend_value in self.appends:
                value = self.amend_append(value, amend_value, evaluate)
        return value

    def amend_if(self, value, evaluate):
        value = copy.copy(value)
        if self.prepend_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if override in self.prepend_if:
                    value = self.amend_prepend(value, self.prepend_if[override],
                                               evaluate)
        if self.append_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in self.scope['OVERRIDES']:
                if override in self.append_if:
                    value = self.amend_append(value, self.append_if[override],
                                              evaluate)
        return value


class MetaString(MetaSequence):

    __slots__ = [ 'expand', 'export' ]

    basetype = basestring
    empty = ''

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


class MetaList(MetaSequence):

    __slots__ = [ 'separator', 'separator_pattern', 'expand' ]

    basetype = list
    empty = []
    fixup_types = [ basestring ]

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

    def __str__(self):
        value = self.get()
        separator = getattr(self, 'separator', ' ')
        if separator is not None:
            return separator.join(value)
        else:
            return str(value)

    def fixup(self, value):
        value = self.scope.expand(value, method=self.expand)
        separator_pattern = getattr(self, 'separator_pattern', '[ \t\n]+')
        value = re.split(separator_pattern, value)
        if value[0] == '':
            value = value[1:]
        if value[-1] == '':
            value = value[:-1]
        return value

    def amend(self, value, evaluate):
        return super(MetaList, self).amend(copy.copy(value), evaluate)

    def amend_if(self, value, evaluate):
        return super(MetaList, self).amend_if(copy.copy(value), evaluate)

    def __add__(self, other):
        value = self.get()
        if not (isinstance(other, type(self)) or
                isinstance(other, MetaString) or
                self.is_fixup_type(other) or
                isinstance(other, self.basetype)):
            raise TypeError(
                "cannot concatenate %s and %s objects"%(
                    type(self), type(other)))
        value = self.copy()
        value.append(other)
        return MetaVar(self.scope, value=value)


class MetaDict(MetaVar):

    __slots__ = [ 'updates', 'update_if', 'expand' ]
    basetype = dict
    empty = {}

    def __init__(self, parent, name=None, value=None):
        assert isinstance(parent, MetaData) or isinstance(parent, MetaDict)
        assert (value is None or
                isinstance(value, MetaDict) or
                isinstance(value, dict))
        self.updates = []
        self.update_if = OverrideDict()
        if isinstance(parent, MetaData):
            self.scope = parent
        else:
            self.scope = parent.scope
            name = '%s.%s'%(parent.name, name)
        super(MetaDict, self).__init__(self.scope, name, {})
        if isinstance(value, dict):
            for key, val in value.iteritems():
                self[key] = val
            return
        else:
            self.expand = 'full'

    def __setitem__(self, key, val):
        if self.value is None:
            self.value = {}
        if self.value.__contains__(key):
            self.value[key].set(val)
            return
        if isinstance(val, dict):
            var = MetaVar(self, key, val)
        else:
            name = '%s.%s'%(self.name, key)
            if type(val) in (str, unicode, list, int, long, bool):
                var = MetaVar(self.scope, name, val)
            elif isinstance(val, MetaVar):
                var = val
                var.name = name
        self.value[key] = var

    def __getitem__(self, key):
        return self.value[key]

    def __delitem__(self, key):
        if self.value is None:
            raise KeyError(key)
        del self.value[key]

    def __len__(self):
        value = self.get()
        if not value:
            return 0
        else:
            return value.__len__()

    def __contains__(self, key):
        value = self.get()
        if not value:
            return False
        else:
            return self.get().__contains__(key)

    def __iter__(self):
        return self.get().__iter__()

    def set(self, value):
        super(MetaDict, self).set(value)
        self.updates = []

    def weak_set(self, value):
        if self.value is None and not self.updates:
            self.cache_invalidate()
            return self.set(value)

    def get(self, evaluate=True):
        if evaluate:
            if self.cache:
                value, deps = self.cache
                self.scope.stack.add_dep(self)
                self.scope.stack.add_deps(deps)
                return value
            else:
                self.scope.stack.push(self)
        try:
            if evaluate:
                value = self.scope.eval(self.value)
                if not (isinstance(value, self.basetype) or
                        value is None):
                    raise TypeError("invalid type in %s %s value: %s"%(
                            type(self).__name__, self.name,
                            type(value).__name__))
            else:
                if self.value is None:
                    value = []
                else:
                    value = [self.value]
            value = self.amend(value, evaluate)
            if self.override_if:
                for override in self.scope['OVERRIDES']:
                    if override in self.override_if:
                        if evaluate:
                            self.scope.stack.clear_deps()
                            value = self.scope.eval(self.override_if[override])
                            if not (isinstance(value, self.basetype) or
                                    value is None):
                                raise TypeError(
                                    "invalid type in %s %s override: %s"%(
                                        type(self).__name__, self.name,
                                        type(value).__name__))
                        else:
                            if self.override_if[override] is None:
                                value = []
                            else:
                                value = [self.override_if[override]]
                        break
                if evaluate:
                    self.scope.stack.add_dep('OVERRIDES')
            value = self.amend_if(value, evaluate)
            if evaluate:
                self.cache_value(value)
        finally:
            if evaluate:
                self.scope.stack.pop()
        if not evaluate:
            if not value:
                return None
            value = ' + '.join(map(
                    lambda v: str(v) if isinstance(v, PythonExpression)
                    else repr(v), value))
        return value

    def items(self):
        value = self.get()
        if not value:
            return []
        else:
            return value.items()

    def keys(self):
        value = self.get()
        if not value:
            return []
        else:
            return value.keys()

    def update(self, *args, **kwargs):
        for value in args:
            if isinstance(value, MetaVar):
                value = value.get()
            if value is None:
                pass
            elif isinstance(value, PythonExpression):
                self.updates.append(value)
            elif isinstance(value, self.basetype):
                self.updates.append(value)
            else:
                raise TypeError('cannot update %s with %s'%(
                        type(self), type(value)))
        if kwargs:
            value = {}
            for key, val in kwargs.iteritems():
                value[key] = self.scope.eval(val)
            self.updates.append(value)

    def amend_update(self, value, amend_value, evaluate):
        if evaluate:
            amend_value = self.scope.eval(amend_value)
        if not amend_value:
            return value
        if value is None:
            value = self.empty
        if evaluate:
            if isinstance(amend_value, self.basetype):
                value.update(amend_value)
            else:
                raise TypeError(
                    "unsupported update_if operation: %s to %s"%(
                        type(amend_value), type(value)))
        else:
            value = value + [amend_value]
        return value

    def amend(self, value, evaluate):
        if self.updates:
            for amend_value in self.updates:
                value = self.amend_update(value, amend_value, evaluate)
        return value

    def amend_if(self, value, evaluate):
        if self.update_if:
            self.scope.stack.add_dep('OVERRIDES')
            for override in reversed(self.scope['OVERRIDES']):
                if override in self.update_if:
                    value = self.amend_update(value, self.update_if[override],
                                              evaluate)
        return value


class MetaBool(MetaVar):

    __slots__ = []
    basetype = bool


class MetaInt(MetaVar):

    __slots__ = []
    basetype = int


class PythonExpression(object):

    __slots__ = [ 'source', 'filename', 'lineno', 'code', 'cacheable' ]

    def __init__(self, source, filename=None, lineno=0, cacheable=True):
        assert isinstance(source, basestring)
        self.source = source
        if lineno != 0:
            source = '\n'*lineno + source
        self.filename = filename
        self.code = compile(source, filename or '<unknown>', 'eval')
        self.cacheable = cacheable

    def __repr__(self):
        return 'PythonExpression(%r)'%(self.source)

    def __str__(self):
        return self.source


import unittest


#class TestCase(unittest.TestCase):
#
#    def setUp(self):
#        self.addTypeEqualityFunc(MetaData, self.assertMetaDataEqual)
#
#    def assertMetaDataEqual(self, x, y, msg=None):
#        print('foobar')
#        if x.signature() == y.signature():
#            return True
#        else:
#            # FIXME: add detailed signature diff information to msg
#            raise self.failureException(msg)


class TestMetaData(unittest.TestCase):

    def setUp(self):
        pass

    def test_init_default(self):
        d = MetaData()
        self.assertIsInstance(d, MetaData)

    def test_str(self):
        d = MetaData()
        self.assertIsInstance(str(d), str)

    def test_stack_str(self):
        d = MetaData()
        self.assertEqual(str(d.stack), '')

    def test_init_metadata(self):
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

    def test_set_str(self):
        d = MetaData()
        d['FOO'] = 'foo'
        self.assertIsInstance(d['FOO'], MetaString)
        self.assertEqual(d['FOO'].get(), 'foo')

    def test_set_list(self):
        d = MetaData()
        d['FOO'] = [1,2]
        self.assertIsInstance(d['FOO'], MetaList)
        self.assertEqual(d['FOO'].get(), [1,2])

    def test_set_list_2(self):
        d = MetaData()
        d['FOO'] = [1,2]
        d['FOO'] = [3,4]
        self.assertIsInstance(d['FOO'], MetaList)
        self.assertEqual(d['FOO'].get(), [3,4])

    def test_set_dict(self):
        d = MetaData()
        d['FOO'] = { 'foo': 42 }
        self.assertIsInstance(d['FOO'], MetaDict)
        self.assertEqual(d['FOO'].get(), { 'foo': 42 })

    def test_set_int(self):
        d = MetaData()
        d['FOO'] = 42
        self.assertIsInstance(d['FOO'], MetaInt)
        self.assertEqual(d['FOO'].get(), 42)

    def test_set_true(self):
        d = MetaData()
        d['FOO'] = True
        self.assertIsInstance(d['FOO'], MetaBool)
        self.assertEqual(d['FOO'].get(), True)

    def test_set_false(self):
        d = MetaData()
        d['FOO'] = False
        self.assertIsInstance(d['FOO'], MetaBool)
        self.assertEqual(d['FOO'].get(), False)

    def test_set_metastring_1(self):
        d = MetaData()
        d['FOO'] = MetaString(d, value='foo')
        self.assertIsInstance(d['FOO'], MetaString)
        self.assertEqual(d['FOO'].get(), 'foo')

    def test_set_invalid_type(self):
        d = MetaData()
        class Foo(object):
            pass
        with self.assertRaises(TypeError):
            d['FOO'] = Foo()

    def test_signature_1(self):
        d = MetaData()
        d['integer'] = 42
        d['string'] = 'Hello world'
        d['list'] = [ 4, 2 ]
        d['map'] = { 'foo': 1, 'bar': 2 }
        sig1 = d.signature()
        del d['list']
        sig2 = d.signature()
        d['list'] = [ 4, 2 ]
        sig3 = d.signature()
        self.assertEqual(sig1, sig3)
        self.assertNotEqual(sig1, sig2)

    def test_signature_2(self):
        d = MetaData()
        d['i'] = 42
        d['s'] = 'Hello world'
        d['list'] = [ 4, 2 ]
        d['map'] = { 'foo': 1, 'bar': 2 }
        sig1 = d.signature(t=dict)
        del d['s']
        sig2 = d.signature(t=dict)
        d['s'] = 'Hello world'
        sig3 = d.signature(t=dict)
        self.assertEqual(sig1, sig3)
        self.assertNotEqual(sig1, sig2)

    def test_signature_3(self):
        d1 = MetaData()
        d1['i'] = 42
        d1['s'] = 'Hello world'
        d1['list'] = [ 4, 2 ]
        d1['map'] = { 'foo': 1, 'bar': 2 }
        d2 = MetaData()
        d2['i'] = 42
        d2['s'] = 'Hello world'
        d2['list'] = [ 4, 2 ]
        d2['map'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d1.signature(), d2.signature())
        d2['foo'] = 'bar'
        self.assertNotEqual(d1.signature(), d2.signature())

    def test_signature_4(self):
        d = MetaData()
        d['i'] = 42
        d['s'] = 'Hello world'
        d['list'] = [ 4, 2 ]
        d['map'] = { 'foo': 1, 'bar': 2 }
        sig1 = d.signature()
        del d['s']
        sig2 = str(d.signature())
        d['s'] = 'Hello world'
        sig3 = str(d.signature())
        self.assertEqual(sig1, sig3)
        self.assertNotEqual(sig1, sig2)

    def test_signature_5(self):
        d = MetaData()
        d['i'] = 42
        with self.assertRaises(TypeError):
            d.signature(t=int)

    def test_signature_6(self):
        d = MetaData()
        d['i'] = 42
        with self.assertRaises(TypeError):
            d.signature(t=list)

    def test_signature_7(self):
        d = MetaData()
        d['i'] = 42
        with self.assertRaises(TypeError):
            d.signature(t=42)

    def test_signature_8(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        self.assertFalse(src == 42)

    def test_flattened_1(self):
        d = MetaData()
        d['FOO'] = 'foo'
        f = d.flattened()
        self.assertEqual(f, {'FOO': 'foo'})

    def test_flattened_2a(self):
        d = MetaData()
        d['D'] = {}
        d['D']['foo'] = [1,2,3]
        d['D']['bar'] = "Hello world!"
        d['D']['foobar'] = {'foo': 1, 'bar': 2}
        d['i'] = 42
        f = d.flattened()
        self.assertEqual(f, {'D': {'foo': [1,2,3], 'bar': 'Hello world!',
                                   'foobar': {'foo': 1, 'bar': 2}},
                             'i': 42})

    def test_flattened_2b(self):
        d = MetaData()
        d['D'] = {}
        d['D']['foo'] = [1,2,3]
        d['D']['bar'] = "Hello world!"
        d['D']['foobar'] = {'foo': 1, 'bar': 2}
        d['D'].expand = 'clean'
        d['i'] = 42
        f = d.flattened()
        self.assertEqual(f, {'D': {'foo': [1,2,3], 'bar': 'Hello world!',
                                   'foobar': {'foo': 1, 'bar': 2}},
                             'i': 42})

    def test_flattened_2c(self):
        d = MetaData()
        d['D'] = {}
        d['D']['foo'] = [1,2,3]
        d['D']['bar'] = "Hello world!"
        d['D']['foobar'] = {'foo': 1, 'bar': 2}
        d['D'].expand = 'partial'
        d['i'] = 42
        f = d.flattened()
        self.assertEqual(f, {'D': {'foo': [1,2,3], 'bar': 'Hello world!',
                                   'foobar': {'foo': 1, 'bar': 2}},
                             'i': 42})


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
        VAR = MetaVar(d, value=MetaVar(d, value='foo'))
        self.assertIsInstance(VAR, MetaString)

    def test_init_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=[42])
        self.assertIsInstance(VAR, MetaList)

    def test_init_metalist(self):
        d = MetaData()
        VAR = MetaVar(d, value=MetaVar(d, value=[42]))
        self.assertIsInstance(VAR, MetaList)

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

    def test_cache_strexpand_depends(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = MetaString(d, value="${FOO}bar")
        self.assertEqual(d['BAR'].get(), 'foobar')
        d['FOO'] = 'fuu'
        self.assertEqual(d['BAR'].get(), 'fuubar')

    def test_cache_python_depends(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = MetaString(d, value=PythonExpression("FOO + 'bar'"))
        self.assertEqual(d['BAR'].get(), 'foobar')
        d['FOO'] = 'fuu'
        self.assertEqual(d['BAR'].get(), 'fuubar')

    def test_signature_1(self):
        d1 = MetaData()
        d1['foobar'] = 'Hello world'
        d2 = MetaData()
        d2['foobar'] = 'Hello world'
        sig1 = d1['foobar'].signature()
        sig2 = str(d2['foobar'].signature())
        self.assertEqual(sig1, sig2)

    def test_signature_2(self):
        d = MetaData()
        d['x'] = 'Hello world'
        sig = d['x'].signature()
        self.assertFalse(sig == 42)

    def test_signature_3(self):
        d = MetaData()
        d['x'] = 'Hello world'
        sig = d['x'].signature()
        self.assertTrue(sig != 42)

    def test_print_1(self):
        d = MetaData()
        import StringIO
        output = StringIO.StringIO()
        d['FOO'] = ['foo']
        d['FOO'].append("bar")
        del d['OVERRIDES']
        d.print(file=output)
        self.assertEqual(output.getvalue(), "FOO = ['foo', 'bar']\n")

    def test_print_2(self):
        d = MetaData()
        import StringIO
        output = StringIO.StringIO()
        d['FOO'] = {'foo': 1}
        del d['OVERRIDES']
        d.print(file=output)
        self.assertEqual(output.getvalue(), "FOO = {'foo': 1}\n")

    def test_is_solitary_1(self):
        d = MetaData()
        d['FOO'] = 'foo'
        self.assertTrue(d.is_solitary('FOO'))

    def test_is_solitary_2a(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = ''
        d['BAR'].set(PythonExpression("FOO + 'bar'"))
        self.assertFalse(d.is_solitary('FOO'))

    def test_is_solitary_2b(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = ''
        d['BAR'].set("${FOO}bar")
        self.assertFalse(d.is_solitary('FOO'))

    def test_is_solitary_3(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = ''
        d['BAR'].set("bar")
        self.assertTrue(d.is_solitary(d['FOO']))
        self.assertTrue(d.is_solitary(d['BAR']))

    def test_is_solitary_4a(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = 'bar'
        self.assertTrue(d.is_solitary(d['FOO']))

    def test_is_solitary_4b(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = 'bar'
        self.assertTrue(d.is_solitary('FOO'))

    def test_is_solitary_5(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['BAR'] = 'bar'
        d['BAR'].override_if['foo'] = '${FOO}'
        self.assertTrue(d.is_solitary('FOO'))
        d['OVERRIDES'].append('foo')
        self.assertFalse(d.is_solitary('FOO'))


class TestMetaInt(unittest.TestCase):

    def setUp(self):
        pass

    def test_var_expand_1(self):
        d = MetaData()
        MetaVar(d, 'FOO', 42)
        self.assertEqual(d['FOO'].get(), 42)



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

    def test_set_code_str_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression('"bar"'))
        self.assertEqual(VAR.get(), 'bar')

    def test_set_code_str_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression('"bar"', lineno=42))
        self.assertEqual(VAR.get(), 'bar')

    def test_set_code_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression('[1,2]'))
        self.assertRaises(TypeError, VAR.get)

    def test_set_code_dict(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression("{'bar': 42}"))
        self.assertRaises(TypeError, VAR.get)

    def test_set_code_bool(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression("'foo'=='bar'"))
        self.assertRaises(TypeError, VAR.get)

    def test_set_code_int(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.set(PythonExpression('6*7'))
        self.assertRaises(TypeError, VAR.get)

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

    def test_prepend_none(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend('foo')
        VAR.prepend(None)
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend(MetaVar(d, value='foo'))
        VAR.prepend(MetaVar(d, value='x'))
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_prepend_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        with self.assertRaises(TypeError):
            VAR.prepend(MetaVar(d, value=[42]))

    def test_prepend_code_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend(value=PythonExpression('[42]'))
        with self.assertRaises(TypeError):
            VAR.get()

    def test_prepend_to_none_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.set(None)
        VAR.prepend('foo')
        self.assertEqual(VAR.get(), 'foo')

    def test_prepend_to_none_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.set(None)
        VAR.prepend('foo')
        self.assertEqual(VAR.get(evaluate=False), "'foo'")

    def test_override_with_none_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.override_if['foo'] = None
        d['OVERRIDES'].append('foo')
        self.assertEqual(VAR.get(evaluate=False), None)

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

    def test_append_none(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append('bar')
        VAR.append(None)
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_metastring(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append(MetaVar(d, value='bar'))
        VAR.append(MetaVar(d, value='x'))
        self.assertEqual(VAR.get(), 'foobarx')

    def test_append_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        with self.assertRaises(TypeError):
            VAR.append(MetaVar(d, value=[42]))

    def test_append_code_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.append(value=PythonExpression('[42]'))
        with self.assertRaises(TypeError):
            VAR.get()

    def test_append_to_none_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.set(None)
        VAR.append('foo')
        self.assertEqual(VAR.get(), 'foo')

    def test_append_to_none_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.set(None)
        VAR.append('foo')
        self.assertEqual(VAR.get(evaluate=False), "'foo'")

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

    def test_add_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        with self.assertRaises(TypeError):
            VAR += [42]

    def test_add_dict(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        with self.assertRaises(TypeError):
            VAR += {'bar': 42}

    def test_add_int(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        with self.assertRaises(TypeError):
            VAR += 42

    def test_add_true(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        with self.assertRaises(TypeError):
            VAR += True

    def test_add_false(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        with self.assertRaises(TypeError):
            VAR += False

    def test_add_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        ADDED = VAR + VAR
        self.assertEqual(ADDED.get(), 'foofoo')
        self.assertEqual(VAR.get(), 'foo')

    def test_add_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        ADDED = VAR + VAR + VAR
        self.assertEqual(ADDED.get(), 'foofoofoo')
        self.assertEqual(VAR.get(), 'foo')

    def test_add_3_mixed(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        ADDED = VAR + 'bar' + VAR
        self.assertEqual(ADDED.get(), 'foobarfoo')
        self.assertEqual(VAR.get(), 'foo')

    def test_add_4(self):
        d = MetaData()
        d['FOO'] = 'foo'
        d['FOO'].override_if['x'] = 'xxx'
        self.assertEqual(d['FOO'].get(), 'foo')
        d['OVERRIDES'] = ['x']
        self.assertEqual(d['FOO'].get(), 'xxx')
        d['FOO'] += 'bar'
        d['OVERRIDES'] = []
        self.assertEqual(d['FOO'].get(), 'foobar')
        d['OVERRIDES'] = ['x']
        self.assertEqual(d['FOO'].get(), 'xxx')

    def test_set_invalid_attr(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_set_code(self):
        d = MetaData()
        VAR = MetaVar(d)
        VAR.set(PythonExpression('"foo" + "bar"'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_code(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.prepend(PythonExpression('"foo"'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_code(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        VAR.append(PythonExpression('"bar"'))
        self.assertEqual(VAR.get(), 'foobar')

    def test_set_code_with_metavars(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        MetaVar(d, 'BAR', 'bar')
        VAR = MetaVar(d)
        VAR.set(PythonExpression('FOO + " " + BAR'))
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
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(VAR.get(), 'foo')

    def test_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.override_if['USE_foo'] = 'foo'
        VAR.override_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foo')

    def test_override_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        VAR.override_if['USE_foo'] = PythonExpression('[42]')
        d['OVERRIDES'] = ['USE_foo']
        self.assertRaises(TypeError, VAR.get)

    def test_prepend_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='bar')
        d['OVERRIDES'] = ['USE_foo']
        VAR.prepend_if['USE_foo'] = 'foo'
        self.assertEqual(VAR.get(), 'foobar')

    def test_prepend_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_bar', 'USE_foo']
        VAR.prepend_if['USE_foo'] = 'foo'
        VAR.prepend_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foobarx')

    def test_prepend_if_metastring_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.prepend_if['USE_foo'] = MetaVar(d, value='foo')
        self.assertEqual(VAR.get(), 'foox')

    def test_prepend_if_metastring_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        a = MetaVar(d, value='foo')
        a += 'bar'
        VAR.prepend_if['USE_foo'] = a
        self.assertEqual(VAR.get(), 'foobarx')

    def test_prepend_if_metastring_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.prepend_if['USE_foo'] = MetaVar(d, value='foo')
        VAR.prepend_if['USE_bar'] = MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'barfoox')

    def test_prepend_if_code_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo']
        VAR.prepend_if['USE_foo'] = PythonExpression('[42]')
        self.assertRaises(TypeError, VAR.get)

    def test_prepend_if_to_none(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        VAR.set(None)
        d['OVERRIDES'] = ['USE_foo']
        VAR.prepend_if['USE_foo'] = 'foo'
        self.assertEqual(VAR.get(), 'foo')

    def test_append_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='foo')
        d['OVERRIDES'] = ['USE_bar']
        VAR.append_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'foobar')

    def test_append_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = 'foo'
        VAR.append_if['USE_bar'] = 'bar'
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_metastring_1(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        self.assertEqual(VAR.get(), 'xfoo')

    def test_append_if_metastring_2(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        a = MetaVar(d, value='foo')
        a += 'bar'
        VAR.append_if['USE_foo'] = a
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_metastring_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        VAR.append_if['USE_bar'] = MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_code_list(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo']
        VAR.append_if['USE_foo'] = PythonExpression('[42]')
        self.assertRaises(TypeError, VAR.get)

    def test_append_if_to_none(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        VAR.set(None)
        d['OVERRIDES'] = ['USE_foo']
        VAR.append_if['USE_foo'] = 'foo'
        self.assertEqual(VAR.get(), 'foo')

    def test_str(self):
        d = MetaData()
        VAR = MetaVar(d, value='foobar')
        self.assertEqual(str(VAR), 'foobar')

    def test_get_invalid_type(self):
        d = MetaData()
        VAR = MetaVar(d, value='')
        VAR.set(PythonExpression('["foo"]'))
        self.assertRaises(TypeError, VAR.get)

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
        MetaVar(d, 'FOOBAR', PythonExpression('FOO + BAR'))
        self.assertEqual(d['FOOBAR'].get(), 'foobar')

    def test_eval_stack_recursive(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', PythonExpression('BAR'))
        BAR = MetaVar(d, 'BAR', PythonExpression('FOO'))
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
        d['FOO'] = 'xfoox'
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

    def test_var_expand_clean_1(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'clean'
        self.assertEqual(d['FOOBAR'].get(), 'foo')

    def test_var_expand_clean_2(self):
        d = MetaData()
        MetaVar(d, 'FOO', 'foo')
        FOOBAR = MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        FOOBAR.expand = 'clean'
        self.assertEqual(d['FOOBAR'].get(), 'foo')
        MetaVar(d, 'BAR', 'bar')
        self.assertEqual(d['FOOBAR'].get(), 'foobar')

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
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(FOO.get(), 'foo')

    def test_var_expand_override(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', '')
        FOO.override_if['USE_foo'] = 'foo'
        MetaVar(d, 'BAR', 'bar')
        MetaVar(d, 'FOOBAR', '${FOO}${BAR}')
        self.assertEqual(d['FOO'].get(), '')
        self.assertEqual(d['FOOBAR'].get(), 'bar')
        d['OVERRIDES'] = ['USE_foo']
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

    def test_print_1(self):
        d = MetaData()
        import StringIO
        output = StringIO.StringIO()
        d['FOO'] = 'foo'
        d['FOO'] += "bar"
        del d['OVERRIDES']
        d.print(file=output)
        self.assertEqual(output.getvalue(), "FOO = 'foobar'\n")

    def test_print_2(self):
        d = MetaData()
        import StringIO
        output = StringIO.StringIO()
        d['FOO'] = 'foo'
        d['FOO'].append('bar')
        del d['OVERRIDES']
        d.print(details=True, file=output)
        self.assertEqual(output.getvalue(),
                         "# FOO = 'foo' + 'bar'\nFOO = 'foobar'\n")

    def test_print_3(self):
        d = MetaData()
        import StringIO
        output = StringIO.StringIO()
        d['FOO'] = 'foo'
        d['FOO'].append('bar')
        d['FOO'].prepend(PythonExpression('BAZ'))
        d['BAZ'] = 'bazzz'
        d['FOO'].override_if['something'] = PythonExpression('HELLO')
        d['HELLO'] = 'Hello world'
        d['HELLO'].append(PythonExpression('BAZ'))
        d['OVERRIDES'].append('something')
        d.print(details=True, file=output)
        lines = output.getvalue().split('\n')
        self.assertTrue("# FOO = HELLO" in lines)
        self.assertTrue("FOO = 'Hello worldbazzz'" in lines)


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

    def test_set_get_ints(self):
        d = MetaData()
        d['D'] = [1,2,3]
        self.assertEqual(d['D'].get(), [1,2,3])

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

    def test_prepend_string(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR.prepend('bar')
        self.assertEqual(VAR.get(), ['bar', 'foo'])

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

    def test_add_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += ['bar', 'x']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_add_metalist(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += MetaVar(d, value=['bar', 'x'])
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_add_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += 'bar'
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_add_metastr(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        VAR += MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_add_int(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        with self.assertRaises(TypeError):
            VAR += 42

    def test_add_true(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        with self.assertRaises(TypeError):
            VAR += True

    def test_add_false(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        with self.assertRaises(TypeError):
            VAR += False

    def test_add_dict(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        with self.assertRaises(TypeError):
            VAR += { 'bar': 42 }

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
        d['OVERRIDES'] = ['USE_foo']
        VAR.override_if['USE_foo'] = ['foo']
        self.assertEqual(VAR.get(), ['foo'])

    def test_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=[])
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.override_if['USE_foo'] = ['foo']
        VAR.override_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo'])

    def test_prepend_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['bar'])
        d['OVERRIDES'] = ['USE_foo']
        VAR.prepend_if['USE_foo'] = ['foo']
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_prepend_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_bar', 'USE_foo']
        VAR.prepend_if['USE_foo'] = ['foo']
        VAR.prepend_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_prepend_if_string(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_foo']
        VAR.prepend_if['USE_foo'] = " foo  \t \n\t bar\n"
        self.assertEqual(VAR.get(), ['foo', 'bar', 'x'])

    def test_append_if_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo'])
        d['OVERRIDES'] = ['USE_bar']
        VAR.append_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['foo', 'bar'])

    def test_append_if_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = ['foo']
        VAR.append_if['USE_bar'] = ['bar']
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_if_metalist_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = MetaVar(d, value=['foo'])
        self.assertEqual(VAR.get(), ['x', 'foo'])

    def test_append_if_metastring_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        a = MetaVar(d, value=['foo'])
        a += ['bar']
        VAR.append_if['USE_foo'] = a
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_append_if_metastring_3(self):
        d = MetaData()
        VAR = MetaVar(d, value='x')
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.append_if['USE_foo'] = MetaVar(d, value='foo')
        VAR.append_if['USE_bar'] = MetaVar(d, value='bar')
        self.assertEqual(VAR.get(), 'xfoobar')

    def test_append_if_string(self):
        d = MetaData()
        VAR = MetaVar(d, value=['x'])
        d['OVERRIDES'] = ['USE_foo']
        VAR.append_if['USE_foo'] = " foo  \t \n\t bar\n"
        self.assertEqual(VAR.get(), ['x', 'foo', 'bar'])

    def test_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar'])
        self.assertEqual(str(VAR), "foo bar")

    def test_str_no_separator(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar'])
        VAR.separator = None
        self.assertEqual(str(VAR), "['foo', 'bar']")

    def test_str_colon_separator(self):
        d = MetaData()
        VAR = MetaVar(d, value=['foo', 'bar'])
        VAR.separator = ':'
        self.assertEqual(str(VAR), "foo:bar")

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

    def test_signature_1(self):
        d = MetaData()
        FOO = MetaList(d, 'FOO', ['foo', 42, [1, 'bar']])
        sig1 = str(FOO.signature())
        FOO.set([7,8])
        sig2 = str(FOO.signature())
        FOO.set(['foo', 42, [1,'bar']])
        sig3 = str(FOO.signature())
        self.assertEqual(sig1, sig3)
        self.assertNotEqual(sig1, sig2)

    def test_signature_2(self):
        d = MetaData()
        FOO = MetaList(d, 'FOO')
        FOO.set(PythonExpression("['bar']"))
        FOO.prepend('x')
        FOO.append('y')
        FOO.override_if['foo'] = [ 1 ]
        FOO.override_if['bar'] = [ 42, 7 ]
        sig1 = str(FOO.signature())
        FOO.set([666])
        sig2 = str(FOO.signature())
        FOO.set(PythonExpression("['bar']"))
        FOO.prepend('x')
        FOO.append('y')
        sig3 = str(FOO.signature())
        self.assertEqual(sig1, sig3)
        self.assertNotEqual(sig1, sig2)

    def test_signature_tuple(self):
        d = MetaData()
        FOO = MetaList(d, 'FOO', [(1, 2)])
        self.assertRaises(TypeError, FOO.signature)

    def test_signature_object(self):
        d = MetaData()
        class FooBar(object):
            pass
        FOO = MetaList(d, 'FOO', [FooBar()])
        self.assertRaises(TypeError, FOO.signature)


class TestMetaDict(unittest.TestCase):

    def setUp(self):
        pass

    def test_init_empty_dict(self):
        d = MetaData()
        MetaVar(d, 'VAR', {})
        self.assertIsInstance(d['VAR'], MetaDict)

    def test_init_dict(self):
        d = MetaData()
        MetaVar(d, 'VAR', {'foo': 1, 'bar': 2})
        self.assertIsInstance(d['VAR'], MetaDict)

    def test_init_dict_get(self):
        d = MetaData()
        MetaVar(d, 'VAR', {'foo': 1, 'bar': 2})
        self.assertEqual(d['VAR'].get(), {'foo': 1, 'bar': 2})

    def test_init_dict_getitem(self):
        d = MetaData()
        MetaVar(d, 'VAR', {'foo': 1, 'bar': 2})
        self.assertIsInstance(d['VAR']['foo'], MetaInt)
        self.assertIsInstance(d['VAR']['bar'], MetaInt)
        self.assertEqual(d['VAR']['foo'].get(), 1)
        self.assertEqual(d['VAR']['bar'].get(), 2)

    def test_init_none(self):
        d = MetaData()
        MetaDict(d, 'VAR', None)
        self.assertIsInstance(d['VAR'], MetaDict)

    def test_init_none_set_get(self):
        d = MetaData()
        MetaDict(d, 'VAR', None)
        d['VAR']['foo'] = 42
        self.assertIsInstance(d['VAR']['foo'], MetaInt)
        self.assertEqual(d['VAR']['foo'].get(), 42)

    def test_assign_1(self):
        d = MetaData()
        d['VAR'] = { 'foo': 1, 'bar': 2 }
        self.assertIsInstance(d['VAR'], MetaDict)
        self.assertIsInstance(d['VAR']['foo'], MetaInt)
        self.assertIsInstance(d['VAR']['bar'], MetaInt)
        self.assertEqual(d['VAR'].get(), {'foo': 1, 'bar': 2})
        self.assertEqual(d['VAR']['foo'].get(), 1)
        self.assertEqual(d['VAR']['bar'].get(), 2)

    def test_get_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d['FOO'].get(), { 'foo': 1, 'bar': 2 })

    def test_get_invalid(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO'].set(PythonExpression('42'))
        with self.assertRaises(TypeError):
            d['FOO'].get()

    def test_get_2(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['BAR'] = {}
        d['BAR'].set(None)
        d['BAR'].update_if['foo'] = PythonExpression('FOO')
        d['OVERRIDES'].append('foo')
        self.assertEqual(d['BAR'].get(), {'foo': 1})
        self.assertEqual(d['BAR'].get(evaluate=False), 'FOO')

    def test_get_3(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['BAR'] = {}
        d['BAR'].update_if['foo'] = PythonExpression('FOO')
        d['OVERRIDES'].append('foo')
        self.assertEqual(d['BAR'].get(evaluate=False), "{} + FOO")

    def test_get_4(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['FOO'].override_if['bar'] = {'bar': 2}
        d['OVERRIDES'].append('bar')
        self.assertEqual(d['FOO'].get(), {'bar': 2})

    def test_get_5(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['FOO'].set(None)
        d['FOO'].override_if['bar'] = {'bar': 2}
        d['OVERRIDES'].append('bar')
        self.assertEqual(d['FOO'].get(), {'bar': 2})

    def test_get_6(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['FOO'].override_if['bar'] = None
        d['OVERRIDES'].append('bar')
        self.assertEqual(d['FOO'].get(), None)

    def test_get_7(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['FOO'].override_if['bar'] = None
        d['OVERRIDES'].append('bar')
        self.assertEqual(d['FOO'].get(evaluate=False), None)

    def test_get_8(self):
        d = MetaData()
        d['FOO'] = {'foo': 1}
        d['FOO'].override_if['bar'] = {'bar': 7}
        d['OVERRIDES'].append('bar')
        self.assertEqual(d['FOO'].get(evaluate=False), "{'bar': 7}")

    # FIXME: add test cases to verify that a value of None updated with {}
    # gives {}, and a value of None updated with None gives None.

    def test_getitem_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d['FOO']['foo'].get(), 1)
        self.assertEqual(d['FOO']['bar'].get(), 2)

    def test_set_1(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 1
        d['FOO']['bar'] = 2
        self.assertEqual(d['FOO']['foo'].get(), 1)
        self.assertEqual(d['FOO']['bar'].get(), 2)

    def test_set_2(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 1
        d['FOO']['foo'] = 2
        self.assertEqual(d['FOO']['foo'].get(), 2)

    def test_set_3(self):
        d = MetaData()
        d['FOO'] = {}
        d['I'] = 2
        d['FOO']['foo'] = d['I']
        self.assertEqual(d['FOO']['foo'].get(), 2)

    def test_set_4(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 1
        d['I'] = 2
        d['FOO']['foo'] = d['I']
        self.assertEqual(d['FOO']['foo'].get(), 2)

    def test_weak_set_1(self):
        d = MetaData()
        VAR = MetaVar(d, value={'FOO': 'foo'})
        self.assertEqual(VAR.get()['FOO'], 'foo')
        VAR.set(None)
        self.assertIsNone(VAR.get())
        VAR.weak_set({'BAR': 'bar'})
        self.assertEqual(VAR.get()['BAR'], 'bar')
        VAR.weak_set({'HELLO': 'world'})
        with self.assertRaises(KeyError):
            VAR.get()['HELLO']
        self.assertEqual(VAR.get()['BAR'], 'bar')

    def test_del_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d['FOO']['foo'].get(), 1)
        del d['FOO']['foo']
        with self.assertRaises(KeyError):
            d['FOO']['foo']

    def test_del_2(self):
        d = MetaData()
        VAR = MetaDict(d, value=None)
        with self.assertRaises(KeyError):
            del VAR['x']

    def test_contains_1(self):
        d = MetaData()
        VAR = MetaVar(d, value={'foo': 1})
        self.assertTrue('foo' in VAR)
        self.assertFalse('bar' in VAR)

    def test_contains_2(self):
        d = MetaData()
        VAR = MetaVar(d, value={'foo': 1})
        VAR.set(None)
        self.assertFalse('foo' in VAR)

    def test_len_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 11, 'bar': 22 }
        self.assertEqual(len(d['FOO']), 2)

    def test_len_2(self):
        d = MetaData()
        d['FOO'] = {}
        self.assertEqual(len(d['FOO']), 0)

    def test_items_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d['FOO'].items(), [('foo', 1), ('bar', 2)])

    def test_items_2(self):
        d = MetaData()
        d['FOO'] = {}
        self.assertEqual(d['FOO'].items(), [])

    def test_keys_1(self):
        d = MetaData()
        d['FOO'] = { 'foo': 1, 'bar': 2 }
        self.assertEqual(d['FOO'].keys(), ['foo', 'bar'])

    def test_keys_2(self):
        d = MetaData()
        d['FOO'] = {}
        self.assertEqual(d['FOO'].keys(), [])

    def test_iter(self):
        d = MetaData()
        VAR = MetaVar(d, value={'foo': 'x', 'bar': 'y'})
        l = set()
        for key in VAR:
            l.add(VAR.get()[key])
        self.assertTrue('x' in l)
        self.assertTrue('y' in l)
        self.assertFalse('z' in l)

    def test_struct_1(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['x'] = {}
        d['FOO']['x']['y'] = 42
        self.assertIsInstance(d['FOO'], MetaDict)
        self.assertIsInstance(d['FOO']['x'], MetaDict)
        self.assertIsInstance(d['FOO']['x']['y'], MetaInt)

    def test_struct_2(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['x'] = {}
        d['FOO']['x']['y'] = {}
        d['FOO']['x']['y']['z'] = 42
        self.assertIsInstance(d['FOO'], MetaDict)
        self.assertIsInstance(d['FOO']['x'], MetaDict)
        self.assertIsInstance(d['FOO']['x']['y'], MetaDict)
        self.assertIsInstance(d['FOO']['x']['y']['z'], MetaInt)
        self.assertEqual(d['FOO']['x']['y']['z'].get(), 42)
        self.assertEqual(d['FOO']['x']['y'].get()['z'], 42)
        self.assertEqual(d['FOO']['x'].get()['y']['z'], 42)
        self.assertEqual(d['FOO'].get()['x']['y']['z'], 42)
        self.assertEqual(d['FOO']['x']['y'].get()['z'], 42)

    def test_update_1(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        d['VAR'].update(FOO='foo')
        self.assertEqual(d['VAR'].get()['BAR'], 'bar')
        self.assertEqual(d['VAR'].get()['FOO'], 'foo')

    def test_update_2(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        d['VAR'].update({'FOO': 'foo'})
        self.assertEqual(d['VAR'].get()['BAR'], 'bar')
        self.assertEqual(d['VAR'].get()['FOO'], 'foo')

    def test_update_3(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        V = MetaVar(d, value={'FOO': 'foo'})
        d['VAR'].update(V)
        self.assertEqual(d['VAR'].get()['BAR'], 'bar')
        self.assertEqual(d['VAR'].get()['FOO'], 'foo')

    def test_update_4(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        MetaVar(d, 'V', {'FOO': 'foo'})
        d['VAR'].update(PythonExpression('V'))
        self.assertEqual(d['VAR'].get()['BAR'], 'bar')
        self.assertEqual(d['VAR'].get()['FOO'], 'foo')

    def test_update_invalid(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        self.assertRaises(TypeError, d['VAR'].update, ([42]))

    def test_update_none(self):
        d = MetaData()
        d['VAR'] = {}
        d['VAR']['BAR'] = 'bar'
        d['VAR'].update(None)
        self.assertEqual(d['VAR'].get()['BAR'], 'bar')

    def test_override_if_1(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 42
        d['FOO'].override_if['USE_not_foo'] = {}
        self.assertEqual(d['FOO']['foo'].get(), 42)
        d['OVERRIDES'] = ['USE_not_foo']
        with self.assertRaises(KeyError):
            d['FOO'].get()['foo'].get()

    def test_override_if_2(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['BAR'] = {}
        d['FOO'].override_if['USE_foo'] = { 'foo': 42 }
        d['FOO']['BAR'].override_if['USE_bar'] = { 'bar': 43}
        with self.assertRaises(KeyError):
            d['FOO'].get()['foo']
        self.assertEqual(d['FOO'].get()['BAR'], {})
        with self.assertRaises(KeyError):
            d['FOO'].get()['BAR']['bar']
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FOO'].get()['foo'], 42)
        with self.assertRaises(KeyError):
            d['FOO'].get()['BAR']
        d['OVERRIDES'] = ['USE_bar']
        with self.assertRaises(KeyError):
            d['FOO'].get()['foo']
        self.assertEqual(d['FOO'].get()['BAR'], { 'bar': 43 })
        self.assertEqual(d['FOO'].get()['BAR']['bar'], 43)
        d['OVERRIDES'] = []
        with self.assertRaises(KeyError):
            d['FOO'].get()['foo']
        self.assertEqual(d['FOO'].get()['BAR'], {})
        with self.assertRaises(KeyError):
            d['FOO'].get()['BAR']['bar']

    def test_override_if_str(self):
        d = MetaData()
        d['FOO'] = {}
        with self.assertRaises(TypeError):
            d['FOO'].override_if['USE_foo'] = "foobar"

    def test_override_if_list(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 42
        with self.assertRaises(TypeError):
            d['FOO'].override_if['USE_foo'] = [42]

    def test_override_if_int(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 42
        with self.assertRaises(TypeError):
            d['FOO'].override_if['USE_foo'] = 42

    def test_override_if_invalid_code(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 42
        d['FOO'].override_if['USE_foo'] = PythonExpression('42')
        d['OVERRIDES'] = ['USE_foo']
        self.assertRaises(TypeError, d['FOO'].get)

    def test_update_if_none(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['BAR'] = {}
        d['FOO'].update_if['USE_foo'] = None
        self.assertEqual(d['FOO'].get()['BAR'], {})
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FOO'].get()['BAR'], {})

    def test_none_update_if_none(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['BAR'] = {}
        d['FOO']['BAR'].set(None)
        d['FOO']['BAR'].update_if['USE_foo'] = { 'foo': 42 }
        self.assertEqual(d['FOO'].get()['BAR'], None)
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FOO'].get()['BAR']['foo'], 42)

    def test_update_if_invalid(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['BAR'] = {}
        d['FOO'].update_if['USE_foo'] = PythonExpression('42')
        self.assertEqual(d['FOO'].get()['BAR'], {})
        d['OVERRIDES'] = ['USE_foo']
        with self.assertRaises(TypeError):
            d['FOO'].get()

    def test_override_and_update_if_1(self):
        d = MetaData()
        d['FOO'] = {}
        d['FOO']['foo'] = 42
        d['FOO'].override_if['USE_not_foo'] = {}
        d['FOO'].update_if['USE_bar'] = { 'bar': 43 }
        self.assertEqual(d['FOO']['foo'].get(), 42)
        with self.assertRaises(KeyError):
            d['FOO'].get()['bar']
        d['OVERRIDES'] = ['USE_not_foo']
        with self.assertRaises(KeyError):
            d['FOO'].get()['foo']
        with self.assertRaises(KeyError):
            d['FOO'].get()['bar']
        d['OVERRIDES'] = ['USE_bar']
        self.assertEqual(d['FOO'].get()['foo'], 42)
        self.assertEqual(d['FOO'].get()['bar'], 43)
        d['OVERRIDES'] = []
        self.assertEqual(d['FOO']['foo'].get(), 42)
        with self.assertRaises(KeyError):
            d['FOO'].get()['bar']

    def test_eval_1(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['${base_bindir}', '${bindir}']
        d['FILES']['${PN}-doc'] = ['${docdir}']
        d['PN'] = 'foo'
        d['base_bindir'] = '/bin'
        d['docdir'] = '${datadir}/doc'
        d['datadir'] = '${prefix}/share'
        d['prefix'] = '/usr'
        d['bindir'] = '${prefix}/bin'
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc']})

    def test_eval_2(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['${base_bindir}', '${bindir}']
        d['FILES']['${PN}-doc'] = ['${docdir}']
        d['FILES']['${PN}-doc'].override_if['USE_foo'] = []
        d['PN'] = 'foo'
        d['base_bindir'] = '/bin'
        d['docdir'] = '${datadir}/doc'
        d['datadir'] = '${prefix}/share'
        d['prefix'] = '/usr'
        d['bindir'] = '${prefix}/bin'
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc']})
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': []})

    def test_eval_3(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['${base_bindir}', '${bindir}']
        d['FILES']['${PN}-doc'] = ['${docdir}']
        d['FILES']['${PN}-doc'].append_if['USE_foo'] = ['more']
        d['PN'] = 'foo'
        d['base_bindir'] = '/bin'
        d['docdir'] = '${datadir}/doc'
        d['datadir'] = '${prefix}/share'
        d['prefix'] = '/usr'
        d['bindir'] = '${prefix}/bin'
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc']})
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc', 'more']})

    def test_eval_4(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['${base_bindir}', '${bindir}']
        d['FILES']['${PN}-doc'] = ['${docdir}']
        d['FILES']['${PN}-doc'].append_if['USE_foo'] = ['more']
        d['PN'] = 'foo'
        d['base_bindir'] = '/bin'
        d['docdir'] = '${datadir}/doc'
        d['datadir'] = '${prefix}/share'
        d['prefix'] = '/usr'
        d['bindir'] = '${prefix}/bin'
        d['FILES'].override_if['USE_foo'] = {}
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc']})
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FILES'].get(), {})

    def test_eval_5(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['${base_bindir}', '${bindir}']
        d['FILES']['${PN}-doc'] = ['${docdir}']
        d['FILES']['${PN}-doc'].append_if['USE_foo'] = ['more']
        d['PN'] = 'foo'
        d['base_bindir'] = '/bin'
        d['docdir'] = '${datadir}/doc'
        d['datadir'] = '${prefix}/share'
        d['prefix'] = '/usr'
        d['bindir'] = '${prefix}/bin'
        d['FILES'].override_if['USE_foo'] = {}
        self.assertEqual(d['FILES'].get(),
                         {'foo': ['/bin', '/usr/bin'],
                          'foo-doc': ['/usr/share/doc']})
        d['OVERRIDES'] = ['USE_foo']
        self.assertEqual(d['FILES'].get(), {})

    def test_eval_duplicate(self):
        d = MetaData()
        d['FILES'] = {}
        d['FILES']['${PN}'] = ['/bin', '/usr/bin']
        d['FILES']['${PN}-doc'] = ['/usr/share/doc']
        d['FILES']['foo'] = ['/sbin', '/usr/sbin']
        d['PN'] = 'foo'
        self.assertRaises(MetaDataDuplicateDictKey, d['FILES'].get)

    def test_signature_1(self):
        d = MetaData()
        FOO = MetaVar(d, 'FOO', {'foo': 42, 'bar': 7})
        sig1 = str(FOO.signature())
        FOO['bar'] = 666
        sig2 = str(FOO.signature())
        FOO['bar'] = 7
        sig3 = str(FOO.signature())
        self.assertNotEqual(sig1, sig2)
        self.assertEqual(sig1, sig3)


class TestMetaBool(unittest.TestCase):

    def setUp(self):
        pass

    def test_init_metavar_true(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertIsInstance(VAR, MetaBool)
        self.assertEqual(VAR.get(), True)

    def test_init_metavar_false(self):
        d = MetaData()
        VAR = MetaVar(d, value=False)
        self.assertIsInstance(VAR, MetaBool)
        self.assertEqual(VAR.get(), False)

    def test_init_none(self):
        d = MetaData()
        VAR = MetaBool(d, value=None)
        self.assertIsInstance(VAR, MetaBool)
        self.assertEqual(VAR.get(), None)

    def test_init_true(self):
        d = MetaData()
        VAR = MetaBool(d, value=True)
        self.assertIsInstance(VAR, MetaBool)
        self.assertEqual(VAR.get(), True)

    def test_init_false(self):
        d = MetaData()
        VAR = MetaBool(d, value=False)
        self.assertIsInstance(VAR, MetaBool)
        self.assertEqual(VAR.get(), False)

    def test_set_get_true(self):
        d = MetaData()
        VAR = MetaBool(d)
        VAR.set(True)
        self.assertEqual(VAR.get(), True)

    def test_set_get_false(self):
        d = MetaData()
        VAR = MetaBool(d)
        VAR.set(False)
        self.assertEqual(VAR.get(), False)

    def test_set_get_0(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertRaises(TypeError, VAR.set, 0)

    def test_set_get_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertRaises(TypeError, VAR.set, 1)

    def test_set_get_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertRaises(TypeError, VAR.set, 2)

    def test_set_get_str(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertRaises(TypeError, VAR.set, ('foobar'))

    def test_set_get_list(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertRaises(TypeError, VAR.set, ([42]))

    def test_set_invalid_attr(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        with self.assertRaises(AttributeError):
            VAR.foo = 'bar'

    def test_override_1(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        d['OVERRIDES'] = ['USE_foo']
        VAR.override_if['USE_foo'] = False
        self.assertEqual(VAR.get(), False)

    def test_override_2(self):
        d = MetaData()
        VAR = MetaVar(d, value=False)
        d['OVERRIDES'] = ['USE_foo', 'USE_bar']
        VAR.override_if['USE_foo'] = True
        VAR.override_if['USE_bar'] = False
        self.assertEqual(VAR.get(), True)

    def test_str_true(self):
        d = MetaData()
        VAR = MetaVar(d, value=True)
        self.assertEqual(str(VAR), "True")

    def test_str_false(self):
        d = MetaData()
        VAR = MetaVar(d, value=False)
        self.assertEqual(str(VAR), "False")

    def test_weak_set_1(self):
        d = MetaData()
        FOO = MetaBool(d, 'FOO', True)
        FOO.weak_set(False)
        self.assertEqual(FOO.get(), True)

    def test_weak_set_2(self):
        d = MetaData()
        FOO = MetaBool(d, 'FOO', False)
        FOO.weak_set(True)
        self.assertEqual(FOO.get(), False)

    def test_weak_set_3(self):
        d = MetaData()
        FOO = MetaBool(d, 'FOO', None)
        FOO.weak_set(False)
        self.assertEqual(FOO.get(), False)

    def test_weak_set_4(self):
        d = MetaData()
        FOO = MetaBool(d, 'FOO', None)
        FOO.weak_set(True)
        self.assertEqual(FOO.get(), True)


class TestPythonExpression(unittest.TestCase):

    def setUp(self):
        pass

    def test_init(self):
        e = PythonExpression('21 * 2')

    def test_repr(self):
        e = PythonExpression('21 * 2')
        self.assertEqual(repr(e), "PythonExpression('21 * 2')")

    def test_str(self):
        e = PythonExpression('21 * 2')
        self.assertEqual(str(e), "21 * 2")

    def test_code(self):
        e = PythonExpression('21 * 2')
        self.assertEqual(eval(e.code), 42)


class TestJSON(unittest.TestCase):

    def setUp(self):
        pass

    def test_1(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        dst = MetaData.loads(src.dumps())
        self.assertEqual(dst['FOO'].get(), 'foo')

    def test_appends(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append('bar')
        dst = MetaData.loads(src.dumps())
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_prepends(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'bar')
        src['FOO'].prepend('foo')
        dst = MetaData.loads(src.dumps())
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_override_if_1(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].override_if['USE_bar'] = 'bar'
        dst = MetaData.loads(src.dumps())
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'foo')
        self.assertEqual(dst['FOO'].get(), 'bar')

    def test_override_if_2(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].override_if['USE_bar'] = 'bar'
        src['FOO'].get()
        dst = MetaData.loads(src.dumps())
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'foo')
        self.assertEqual(dst['FOO'].get(), 'bar')

    def test_prepend_if(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'bar')
        src['FOO'].prepend_if['USE_bar'] = 'foo'
        dst = MetaData.loads(src.dumps())
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'bar')
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_append(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append_if['USE_bar'] = 'bar'
        dst = MetaData.loads(src.dumps())
        dst['OVERRIDES'].append(['USE_bar'])
        self.assertEqual(src['FOO'].get(), 'foo')
        self.assertEqual(dst['FOO'].get(), 'foobar')

    def test_signature_1(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src_json = src.dumps()
        dst = MetaData.loads(src_json)
        self.assertEqual(src, dst)

    def test_signature_2(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        dst = MetaData.loads(src.dumps())
        src['FOO'].set('bar')
        self.assertNotEqual(src, dst)

    def test_signature_3(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        dst = MetaData.loads(src.dumps())
        src['FOO'].override_if['nothing'] = 'bar'
        self.assertNotEqual(src, dst)

    def test_signature_4(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].override_if['nothing'] = 'bar'
        dst = MetaData.loads(src.dumps())
        self.assertEqual(src, dst)

    def test_signature_5(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].override_if['nothing'] = 'bar'
        dst = MetaData.loads(src.dumps())
        self.assertEqual(src['FOO'].signature(), dst['FOO'].signature())
        self.assertEqual(src, dst)
        del src['FOO'].override_if['nothing']
        self.assertNotEqual(src, dst)

    def test_signature_6(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append_if['nothing'] = '1'
        src['FOO'].override_if['nothing'] = 'bar'
        src['FOO'].prepend_if['nothing'] = '2'
        dst = MetaData.loads(src.dumps())
        self.assertEqual(src, dst)
        del src['FOO'].append_if['nothing']
        self.assertNotEqual(src, dst)
        src['FOO'].append_if['nothing'] = '1'
        self.assertEqual(src, dst)

    def test_signature_7(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append_if['nothing'] = '1'
        src['FOO'].override_if['nothing'] = 'bar'
        src['FOO'].prepend_if['nothing'] = '2'
        dst = MetaData.loads(src.dumps())
        self.assertFalse(src != dst)
        del src['FOO'].append_if['nothing']
        self.assertTrue(src != dst)

    def test_signature_8(self):
        src = MetaData()
        MetaVar(src, 'FOO', 'foo')
        src['FOO'].append_if['nothing'] = '1'
        src['FOO'].override_if['nothing'] = 'bar'
        src['FOO'].prepend_if['nothing'] = '2'
        dst = MetaData.loads(src.dumps())
        self.assertTrue(src == dst)
        del src['FOO'].append_if['nothing']
        self.assertFalse(src == dst)


if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
