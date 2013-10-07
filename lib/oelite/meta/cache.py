import oelite.recipe
import oelite.log
import oelite.path

import os
import cPickle
import random

log = oelite.log.get_logger()


# FIXME: refactor into separate recipe and task cache classes, or do something
# else to create a more natural API.
# No, refactor into a proper recipe cache, with functions for load and save of tasks.

class MetaCache:

    """Object representing a cache (file) of a parsed OE-lite recipe.

    Each cache can only hold different types of the same recipes.  If a recipe
    file defines both a 'native' and 'machine' type recipe, a single cache
    should be used for holding both of these recipes.  For recipes from
    different recipe files, separate caches must be used.

    """

    def __init__(self, config, recipe, recipes=None):
        """Constructor for OE-lite metadata cache files.

        Arguments:
        config -- configuration metadata.
        recipe -- path to the recipe file, OEliteRecipe or OEliteTask.

        Keyword arguments:
        recipes -- dictionary of recipes to put in cache, indexed by recipe
            type as key (ie. 'native', 'machine', and so on), and values of
            type oelite.MetaData.  If None, recipes will be read from cache.

        """
        if isinstance(recipe, oelite.recipe.OEliteRecipe):
            self.recipe_file = recipe.filename
        else:
            self.recipe_file = recipe
        self.recipe_cache = os.path.join(
            config.get('PARSERDIR'),
            oelite.path.relpath(self.recipe_file) + ".cache")

    def __repr__(self):
        return '%s()'%(self.__class__.__name__)

    #def __iter__(self):
    #    return self.meta.keys().__iter__()

    def task_cache(self, task):
        """Get filename of task cache file."""
        return self.recipe_cache + '.%s.%s'%(task.recipe.type, task.name)

    def exists(self):
        """Check if cache file exists.

        Return True if underlying cache file exists, False otherwise.

        """
        return os.path.exists(self.recipe_cache)

    def is_current(self, env_signatures):
        """Check if cache exists and is current.

        Arguments:
        env_signatures -- list of signatures to consider as current.

        Return True if recipe or task cache file exists and is
        current. Current state is determined based on source signature,
        environment signature, and mtime of recipe input files.

        """
        if not self.exists():
            return False
        if not self._preload():
            return False
        try:
            if src_signature() != self.src_signature:
                return False
            if not self.env_signature in env_signatures:
                return False
            if not isinstance(self.mtimes, set):
                return False
        except AttributeError:
            return False
        for (fn, oepath, old_mtime) in list(self.mtimes):
            if oepath:
                filepath = oelite.path.which(oepath, fn)
            else:
                assert os.path.isabs(fn)
                filepath = fn
            if os.path.exists(filepath):
                cur_mtime = os.path.getmtime(filepath)
            else:
                cur_mtime = None
            if cur_mtime != old_mtime:
                return False
        return True

    def has_task(self, task):
        """Check if cache has valid task cache file."""
        if not self._preload():
            return False
        task_cache = self.task_cache(task)
        if not os.path.exists(task_cache):
            return False
        with open(task_cache, 'r') as cachefile:
            token = cPickle.load(cachefile)
            if token == self.token:
                return True
        return False
    
    def clean(self):
        """Remove the underlying cache file (if it exists)."""
        if self.exists():
            log.debug("Removing stale metadata cache: %s", self.recipe_cache)
            os.remove(self.recipe_cache)
        # FIXME: rewrite to use glob.glob to remote task cache files also
        return

    def load(self, cookbook=None):
        """Load OE-lite recipe or metadata from cache file.

        Arguments:
        cookbook - oelite.cookbook.CookBook instance to create the recipe in.

        """
        if not self._preload():
            return None
        recipes = {}
        num_recipes = cPickle.load(self.file)
        for i in xrange(num_recipes):
            recipe = oelite.recipe.unpickle(
                self.file, self.recipe_file, cookbook)
            recipes[recipe.type] = recipe
        self.file.close()
        del self.file
        return recipes

    def load_task(self, task):
        """Load OE-lite task metadata from cache file.

        Arguments:
        task - oelite.task.OEliteTask instance to load.

        """
        if not self._preload():
            return False
        task_cache = self.task_cache(task)
        with open(task_cache, 'r') as cachefile:
            token = cPickle.load(cachefile)
            if token != self.token:
                return None
            signature = cPickle.load(cachefile)
            meta = oelite.meta.dict.unpickle(cachefile)
        task.signature = signature
        task.meta = meta
        return True

    def _preload(self):
        """Load the cache preample as needed."""
        attrs = ('src_signature', 'env_signature', 'mtimes', 'token')
        if hasattr(self, 'file'):
            for attr in attrs:
                assert hasattr(self, attr)
            return True
        try:
            self.file = open(self.recipe_cache)
        except:
            return False
        try:
            for attr in attrs:
                setattr(self, attr, cPickle.load(self.file))
        except:
            for attr in attrs:
                if hasattr(self, attr):
                    delattr(self, attr)
            self.file.close()
            delattr(self, 'file')
            return False
        return True

    def save(self, env_signature, recipes):
        """Save OE-lite metadata recipes to cache file.

        Arguments:
        env_signature -- environment variable signature.
        recipes -- dictionary of recipes to put in cache, indexed by recipe
            type as key (ie. 'native', 'machine', and so on), and values of
            type oelite.MetaData.

        """
        oelite.util.makedirs(os.path.dirname(self.recipe_cache))
        mtimes = set()
        for type in recipes:
            for mtime in recipes[type].get_input_mtimes():
                mtimes.add(mtime)
        token = '%032x'%(random.getrandbits(128))
        with open(self.recipe_cache, "w") as cachefile:
            cPickle.dump(src_signature(), cachefile, 2)
            cPickle.dump(env_signature, cachefile, 2)
            cPickle.dump(mtimes, cachefile, 2)
            cPickle.dump(token, cachefile, 2)
            cPickle.dump(len(recipes), cachefile, 2)
            for recipe_type, recipe_meta in recipes.items():
                cPickle.dump(recipe_type, cachefile, 2)
                recipe_meta.pickle(cachefile)
        return

    def save_task(self, task):
        """Save OE-lite task metadata to cache file.

        Arguments:
        task - oelite.task.OEliteTask instance to save.

        """
        # FIXME: figure out how to handle __dont_cache=True recipes
        # (like base-version.oe)
        if self._preload():
            token = self.token
        else:
            token = ''
        with open(self.task_cache(task), 'w') as cachefile:
            cPickle.dump(token, cachefile, 2)
            cPickle.dump(task.signature, cachefile, 2)
            task.meta.pickle(cachefile)
        return


SRC_MODULES = [
    "oelite.meta",
    "oelite.meta.meta",
    "oelite.meta.dict",
    "oelite.meta.cache",
    "oelite.parse",
    "oelite.parse.oelex",
    "oelite.parse.oeparse",
    "oelite.parse.confparse",
    "oelite.parse.expandlex",
    "oelite.parse.expandparse",
    "oelite.fetch",
    "oelite.fetch.fetch",
    "oelite.fetch.sigfile",
    "oelite.fetch.local",
    "oelite.fetch.url",
    "oelite.fetch.git",
    "oelite.fetch.svn",
    "oelite.fetch.hg",
    "oelite",
    "oelite.arch",
    "oelite.baker",
    "oelite.cookbook",
    "oelite.dbutil",
    "oelite.function",
    "oelite.item",
    "oelite.package",
    "oelite.pyexec",
    "oelite.recipe",
    "oelite.runq",
    "oelite.task",
    "oelite.util",
    "oelite.meta",
    "oelite.meta.cache",
    ]


def src_signature():
    """Return hash signature of all source modules.

    Return message digest of source files for all Python modules in
    SRC_MODULES. The return value is a string which may contain non-ASCII
    characters, including null bytes.

    The digest is only generated once. All following calls to src_digest()
    returns a cached value.

    """
    global _src_digest
    if _src_digest:
        return _src_digest
    import inspect
    import hashlib
    files = []
    for module in SRC_MODULES:
        exec "import %s"%(module)
        files.append(inspect.getsourcefile(eval(module)))
    m = hashlib.md5()
    for filename in files:
        with open(filename) as file:
            m.update(file.read())
    _src_digest = m.digest()
    return _src_digest

_src_digest = None
