import sys
import re

from collections import MutableMapping

import logging
log = logging.getLogger()


OE_ENV_WHITELIST = [
    "PATH",
    "PWD",
    "SHELL",
    "TERM",
]


class MetaVariable(object):


    # FIXME: __slots__ = [ 'value', 'prepend', 'append', 'override_if',
    # 'prepend_if', 'append_if', 'ifs', ... ]

    def __init__(self, name, value=None):
        self.__name__ = name
        self.value = value
        self.prepend = []
        self.append = []
        #if value is not None:
        #    self.type = type(value)
        #else:
        #    self.type = None
        self.override_if = {}
        self.prepend_if = {}
        self.append_if = {}


    def __repr__(self):
        return '%s(%s)'%(self.__class__, self.__name__)


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


    def set(self, value):
        self.value = value
        self.prepend = []
        self.append = []

    def get(self, evaluate=True, override=True, amend=True):
        assert not ((amend or override) and not evaluate)
        value = self.value
        if evaluate:
            value = self.__eval__(value)
        if amend and self.prepend:
            if not type(value) in ('str', 'list'):
                raise TypeError(
                    "prepend to %s not supported: %r"%(type(value), self))
            for amend_value in map(self.__eval__, self.prepend):
                if type(value) == type(amend_value):
                    value = amend_value + value
                elif (isinstance(value, list) and
                      isinstance(amend_value, str)):
                    ifs = getattr(self, 'ifs', '\s+')
                    value = re.split(ifs, amend_value) + value
                else:
                    raise TypeError(
                        "unsupported prepend operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        if amend and self.append:
            if not type(value) in ('str', 'list'):
                raise TypeError(
                    "append to %s not supported: %r"%(type(value), self))
            for amend_value in map(self.__eval__, self.append):
                if type(value) == type(amend_value):
                    value += amend_value
                elif (isinstance(value, list) and
                      isinstance(amend_value, str)):
                    ifs = getattr(self, 'ifs', '\s+')
                    value += re.split(ifs, amend_value)
                else:
                    raise TypeError(
                        "unsupported append operation: %s to %s: %r"%(
                            type(amend_value), type(value), self))
        # FIXME: implement override_if, prepend_if, append_if handling
        

class MetaData(MutableMapping):

    FLAGS = ('dirs', 'cleandirs')
    INDEXED_FLAGS = ('python', 'task', 'precondition', 'export')

    def __init__(self, d=None):
        super(MetaData, self).__init__()
        if d is None:
            pass
        elif isinstance(d, dict):
            self.import_dict(d)
        else:
            raise Exception("invalid argument: meta=%s"%(repr(meta)))
        # key -> value, flags, override_if, prepend_if, append_if
        self.vars = {}
        self.flag_index = {}
        return

    def import_dict(self, d):
        for key, value in d:
            self.set(key, value)

    def __repr__(self):
        return '%s()'%(self.__class__.__name__)

    def __setitem__(self, key, value): # required by MutableMapping
        self.set(key, value)
        return value

    def __getitem__(self, key): # required by Mapping
        return self.get(key)

    def __delitem__(self, key): # required by MutableMapping
        del self.vars[key]

    def __iter__(self): # required by Iterable
        return self.get_vars().__iter__()

    def __len__(self): # required by Sized
        return len(self.vars)

    def __contains__(self, item): # required by Container
        return self.get(item, False) is not None

    def set(self, key, value):
        assert value in (str, dict, list, bool, code) #FIXME: where is code???
        if not key in self.vars:
            if value is not None:
                self.vars[key] = [ [value], {}, {}, {}, {} ]
        else:
            self.vars[key][0] = [value]

    def get(self, key, default=None, evaluate=True, override=True, amend=True):
        """Get variable value."""
        raise Exception("Not implemented yet")

    def set_flag(self, var, flag, value):
        if not var in self.vars:
            if value is not None:
                self.vars[var] = [ [], { flag: value }, {}, {}, {} ]
        else:
            self.vars[var][1][flag] = value

    def get_flag(self, var, flag):
        try:
            return self.vars[var][1][flag]
        except KeyError:
            return None

    def set_override_if(self, var, condition, value):
        if not var in self.vars:
            if value is not None:
                self.vars[var] = [ [], {}, { condition: value }, {}, {} ]
        else:
            self.vars[var][2][condition] = value

    def get_override_if(self, var, condition):
        try:
            return self.vars[var][2][condition]
        except KeyError:
            return None

    def set_prepend_if(self, var, condition, value):
        if not var in self.vars:
            if value is not None:
                self.vars[var] = [ [], {}, {}, { condition: value }, {} ]
        else:
            self.vars[var][3][condition] = value

    def get_prepend_if(self, var, condition):
        try:
            return self.vars[var][3][condition]
        except KeyError:
            return None

    def set_append_if(self, var, condition, value):
        if not var in self.vars:
            if value is not None:
                self.vars[var] = [ [], {}, {}, {}, { condition: value } ]
        else:
            self.vars[var][4][condition] = value

    def get_append_if(self, var, condition):
        try:
            return self.vars[var][4][condition]
        except KeyError:
            return None

    def import_env(self):
        whitelist = OE_ENV_WHITELIST
        if "OE_ENV_WHITELIST" in os.environ:
            whitelist += os.environ["OE_ENV_WHITELIST"].split()
        if "OE_ENV_WHITELIST" in self:
            whitelist += self.get("OE_ENV_WHITELIST", True).split()
        log.debug("whitelist=%s", whitelist)
        hasher = hashlib.md5()
        for var in whitelist:
            if not var in self.values and var in os.environ:
                env_val = os.environ[var]
                self.values[var] = env_val
                log.debug("ENV> %s=%s", var, env_val)
                hasher.update("%s=%r\n"%(var, env_val))
        self.set('__env_signature', hasher.hexdigest())
        self.set_flag('__env_signature', 'nohash', True)



    def env_signature(self):
        return self.get('__env_signature')

    def get_vars(self, flag=None, allow_unset=False):
        if flag is not None:
            if flag in self.flag_index:
                vars = self.flag_index[flag]
            else:
                log.debug("get_vars: flag %s not indexed", flag)
                vars = (self.values.keys() + self.override_if.keys() +
                        self.append_if.keys() + self.prepend_if())
                def var_is_flagged(var):
                    try:
                        return bool(self.flags[var][flag])
                    except KeyError:
                        return False
                vars = filter(var_is_flagged, vars)
        else:
            log.debug("get_vars: doing expensive list of all variables", flag)
            vars = (self.values.keys() + self.override_if.keys() +
                    self.append_if.keys() + self.prepend_if())
        if not allow_unset():
            def var_is_not_none(var):
                return self.get(var) is not None
            vars = filter(var_is_not_none, vars)
        return sorted(vars)

    def append(self, var, value):
        if not var in self.values:
            self.vars[var] = [ [value], {}, {}, {}, {} ]
            return
        self.values[var][0].append(value)

    def prepend(self, var, value):
        if not var in self.values:
            self.vars[var] = [ [value], {}, {}, {}, {} ]
            return
        self.values[var][0].insert(0, value)

    # FIXME: what if the variable is actually a list?  appending of [3,4] to a
    # variable with value [1,2] should yield [1,2,3,4], and not [1,2,[3,4]].

    # FIXME: find out a way to store main value, so that the type of that can
    # decide how to append and prepend, ie. if it should be fx. list style or
    # string style.  The self.vars[*] lists could be extended to have a
    # prepends list, the main value, and an appends list, instead of just a
    # values list.  This way, instead of inventing some new syntax for setting
    # variable type, you can do:
    #   FOO = ""
    #   FOO += "foo"
    # and
    #   BAR = []
    #   BAR += "bar"
    # yielding
    #   FOO = "foo"
    #   BAR = ["bar"]
    # and with string splitting
    #   FOOBAR = []
    #   FOOBAR.ifs = " "
    #   FOOBAR += "foo bar"
    # yielding
    #   FOOBAR = ["foo", "bar"]

    # FIXME: in order to be able to handle lazy evaluation of variable flags,
    # overrides_if, and so on, something similar with lists like above might
    # be needed also.

    def append_flag(self, var, flag, value, separator=""):
        current = self.get_flag(var, flag)
        if current is None:
            self.set_flag(var, flag, value)
        else:
            self.set_flag(var, flag, value + separator + current)

    def prepend_override(self, var, override, value, separator=""):
        current = self.get_override(var, override)
        if current is None:
            self.set_override(var, override, value)
        else:
            self.set_override(var, override, value + separator + current)


    builtin_nohash = [
        "OE_REMOTES",
        "OE_MODULES",
        "OE_ENV_WHITELIST",
        "PATH",
        "PWD",
        "SHELL",
        "TERM",
        "TOPDIR",
        "TMPDIR",
        "OEPATH",
        "OEPATH_PRETTY",
        "OERECIPES",
        "OERECIPES_PRETTY",
        "FILE",
        "COMPATIBLE_BUILD_ARCHS",
        "COMPATIBLE_HOST_ARCHS",
        "COMPATIBLE_TARGET_ARCHS",
        "COMPATIBLE_BUILD_CPU_FAMILIES",
        "COMPATIBLE_HOST_CPU_FAMILIES",
        "COMPATIBLE_TARGET_CPU_FAMILIES",
        "COMPATIBLE_MACHINES",
        "INCOMPATIBLE_RECIPES",
        "COMPATIBLE_IF_FLAGS",
        "_task_deps",
    ]

    builtin_nohash_prefix = [
        "OE_REMOTE_",
        "OE_MODULE_",
    ]

    def dump_var(self, key, o=sys.__stdout__, pretty=True, dynvars={},
                 flags=False, ignore_flags=None):
        if pretty:
            eol = "\n\n"
        else:
            eol = "\n"

        var_flags = sorted(self.get_flags(key).items())

        if flags:
            if ignore_flags:
                ignore_flags = re.compile("|".join(ignore_flags))
            for flag,val in var_flags:
                if flag == "expand":
                    continue
                if ignore_flags and ignore_flags.match(flag):
                    continue
                if pretty and flag in ("python", "bash", "export"):
                    continue
                o.write("%s[%s]=%r\n"%(key, flag, val))

        if self.get_flag(key, "python"): # FIXME: use _flags
            func = "python"
        elif self.get_flag(key, "bash"): # FIXME: use _flags
            func = "bash"
        else:
            func = None

        expand = self.get_flag(key, "expand") # FIXME: use _flags
        if expand is not None:
            expand = int(expand)
        elif func == "python":
            expand = False
        else:
            expand = FULL_EXPANSION
        if not expand and func != "python":
            expand = OVERRIDES_EXPANSION
        val = self.get(key, expand)

        if not val:
            return 0

        val = str(val)

        for dynvar_name, dynvar_val in dynvars:
            val = string.replace(val, dynvar_val, "${%s}"%(dynvar_name))

        if pretty and expand and expand != OVERRIDES_EXPANSION:
            o.write("# %s=%r\n"%(key, self.get(key, OVERRIDES_EXPANSION)))

        if func == "python":
            o.write("def %s(%s):\n%s"%(
                    key, self.get_flag(key, "args"), val))
            return

        if func == "bash":
            o.write("%s() {\n%s}%s"%(key, val, eol))
            return

        if pretty and self.get_flag(key, "export"):
            o.write("export ")

        o.write("%s=%s%s"%(key, repr(val), eol))
        return


    def dump(self, o=sys.__stdout__, pretty=True, nohash=False, only=None,
             flags=False, ignore_flags=None):

        dynvars = []
        for varname in ("WORKDIR", "TOPDIR", "DATETIME",
                        "MANIFEST_ORIGIN_URL", "MANIFEST_ORIGIN_SRCURI",
                        "MANIFEST_ORIGIN_PARAMS"):
            varval = self.get(varname, True)
            if varval:
                dynvars.append((varname, varval))

        keys = sorted((key for key in self.keys() if not key.startswith("__")))
        for key in keys:
            if only and key not in only:
                continue
            if not nohash:
                if key in self.builtin_nohash:
                    continue
                if self.get_flag(key, "nohash"):
                    continue
                nohash_prefixed = False
                for prefix in self.builtin_nohash_prefix:
                    if key.startswith(prefix):
                        nohash_prefixed = True
                        break
                if nohash_prefixed:
                    continue
            self.dump_var(key, o, pretty, dynvars, flags, ignore_flags)


    def get_function(self, name):
        if not name in self or not self.get(name):
            return oelite.function.NoopFunction(self, name)
        if self.get_flag(name, "python"):
            return oelite.function.PythonFunction(self, name)
        else:
            return oelite.function.ShellFunction(self, name)


    def signature(self, ignore_flags=("__", "emit$", "omit$", "filename"),
                  force=False, dump=None):
        import hashlib

        if self._signature and not force:
            return self._signature

        class StringOutput:
            def __init__(self):
                self.blob = ""
            def write(self, msg):
                self.blob += str(msg)
            def __len__(self):
                return len(self.blob)

        class StringHasher:
            def __init__(self, hasher):
                self.hasher = hasher
            def write(self, msg):
                self.hasher.update(str(msg))
            def __str__(self):
                return self.hasher.hexdigest()

        hasher = StringHasher(hashlib.md5())

        if dump:
            assert isinstance(dump, basestring)
            dumper = StringOutput()
            self.dump(dumper, pretty=False, nohash=False,
                      flags=True, ignore_flags=ignore_flags)
            dumpdir = os.path.dirname(dump)
            if dumpdir and not os.path.exists(dumpdir):
                os.makedirs(dumpdir)
            open(dump, "w").write(dumper.blob)
        self.dump(hasher, pretty=False, nohash=False,
                  flags=True, ignore_flags=ignore_flags)

        self._signature = str(hasher)
        return self._signature


if __name__ == "__main__":
    logging.basicConfig()
    sys.exit(0)
