import oelite.fetch
import fetching.hg_cache
import os
import re
import warnings

class HgFetcher():

    SUPPORTED_SCHEMES = ("hg")
    CHANGESET_ID_RE = re.compile("[0-9a-f]{1,40}")

    def __init__(self, uri, d):
        if not uri.scheme in self.SUPPORTED_SCHEMES:
            raise Exception(
                "Scheme %s not supported by oelite.fetch.HgFetcher"%(scheme))
        self.uri = uri
        self.url = "%s://%s"%("hg", uri.location)
        repo_name = uri.location.split("/")[-1]
        try:
            self.repo = uri.params["repo"]
        except KeyError:
            self.repo = repo_name
        if not "/" in self.repo:
            self.repo = os.path.join(uri.isubdir, self.repo)
        if not os.path.isabs(self.repo):
            self.repo = os.path.join(uri.ingredients, self.repo)
        self.changeset = None
        self.tag = None
        self.branch = None
        if "changeset" in uri.params:
            self.changeset = uri.params["changeset"]
            if not self.CHANGESET_ID_RE.match(self.changeset):
                raise oelite.fetch.InvalidURI(
                    self.uri, "invalid changeset %s"%(repr(self.changeset)))
        if "tag" in uri.params:
            self.tag = uri.params["tag"]
            self.signature_name = self.url
            self.signature_name += ";tag=" + self.tag
        if "branch" in uri.params:
            self.branch = uri.params["branch"]
        i = bool(self.changeset) + bool(self.tag) + bool(self.branch)
        if i == 0:
            self.branch = "HEAD"
        elif i != 1:
            raise oelite.fetch.InvalidURI(
                self.uri, "cannot mix changeset, tag and branch parameters")
        if "track" in uri.params:
            self.track = uri.params["track"].split(",")
            warnings.warn("track parameter not implemented yet")
        else:
            self.track = None
        if "subdir" in uri.params:
            self.dest = uri.params["subdir"]
            if subdir[-1] == "/":
                self.dest += repo_name
        else:
            self.dest = repo_name
        self.dest = os.path.join(d.get("SRCDIR"), self.dest)
        self.signatures = d.get("FILE") + ".sig"
        self.fetch_signatures = d["__fetch_signatures"]
        return

    def signature(self):
        if self.changeset:
            return self.changeset
        elif self.tag:
            try:
                self._signature = self.fetch_signatures[self.signature_name]
                return self._signature
            except KeyError:
                raise oelite.fetch.NoSignature(self.uri, "signature unknown")
        elif self.branch:
            warnings.warn("fetching mercurial branch head, causing source signature to not be sufficient for proper signature handling")
            return ""
        raise Exception("this should not be reached")

    def get_cache(self):
        try:
            return self.cache
        except AttributeError:
            self.cache = fetching.hg_cache.Fetcher(self.url, cache=self.repo)
            return self.cache

    def fetch(self):
        cache = self.get_cache()
        cache.setup_cache()
        if (self.branch or
            (self.tag and not cache.has_tag(self.tag)) or
            (self.changeset and not cache.has_changeset(self.changeset))):
            try:
                cache.update()
            except:
                print "Error fetching hg remote: %s"%(self.url,)
                return False
        if self.tag:
            changeset = cache.query_tag(self.tag)
            if not changeset:
                raise oelite.fetch.FetchError(self.uri, "unknown tag: %s"%(self.tag))
            changeset = changeset.hexsha # FIXME: hexsha is a GitPython attribute
            if not "_signature" in dir(self):
                return (self.signature_name, changeset)
            return changeset == self._signature
        return True

    def unpack(self):
        cache = self.get_cache()
        rev = self.changeset or self.tag or self.branch
        cache.download(self.dest, rev=rev, force=True)
        return True
