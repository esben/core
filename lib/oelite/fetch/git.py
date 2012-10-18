import oelite.fetch
import fetching.git_cache
import os
import re
import warnings
import string

class GitFetcher():

    SUPPORTED_SCHEMES = ("git")
    COMMIT_ID_RE = re.compile("[0-9a-f]{1,40}")

    def __init__(self, uri, d):
        if not uri.scheme in self.SUPPORTED_SCHEMES:
            raise Exception(
                "Scheme %s not supported by oelite.fetch.GitFetcher"%(scheme))
        uri.fdepends.append("native:git")
        self.uri = uri
        try:
            protocol = uri.params["protocol"]
        except KeyError:
            protocol = "git"
        self.url = "%s://%s"%(protocol, uri.location)
        self.mirror_name = "%s_%s"%(protocol, uri.location.translate(string.maketrans("/", "_")))
        if self.mirror_name.endswith(".git"):
            self.mirror_name = self.mirror_name[:-4]
        try:
            self.remote = uri.params["origin"]
        except KeyError:
            self.remote = "origin"
        repo_name = uri.location.split("/")[-1]
        try:
            self.repo = uri.params["repo"]
        except KeyError:
            self.repo = repo_name
        if not "/" in self.repo:
            self.repo = os.path.join(uri.isubdir, self.repo)
        if not os.path.isabs(self.repo):
            self.repo = os.path.join(uri.ingredients, self.repo)
        self.commit = None
        self.tag = None
        self.branch = None
        if "commit" in uri.params:
            self.commit = uri.params["commit"]
            if not self.COMMIT_ID_RE.match(self.commit):
                raise oelite.fetch.InvalidURI(
                    self.uri, "invalid commit id %s"%(repr(self.commit)))
        if "tag" in uri.params:
            self.tag = uri.params["tag"]
            self.signature_name = "git://" + uri.location
            if protocol != "git":
                self.signature_name += ";protocol=" + protocol
            self.signature_name += ";tag=" + self.tag
        if "branch" in uri.params:
            self.branch = uri.params["branch"]
        i = bool(self.commit) + bool(self.tag) + bool(self.branch)
        if i == 0:
            self.branch = "HEAD"
        elif i != 1:
            raise oelite.fetch.InvalidURI(
                self.uri, "cannot mix commit, tag and branch parameters")
        if "track" in uri.params:
            self.track = uri.params["track"].split(",")
            warnings.warn("track parameter not implemented yet")
        else:
            self.track = None
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        if "subdir" in uri.params:
            self.dest = uri.params["subdir"]
            if self.dest[-1] == "/":
                self.dest += repo_name
        else:
            self.dest = repo_name
        try:
            self.remote = uri.params["remote"]
        except KeyError:
            self.remote = None
        self.signatures = d.get("FILE") + ".sig"
        self.fetch_signatures = d["__fetch_signatures"]
        return

    def signature(self):
        if self.commit:
            return self.commit
        elif self.tag:
            try:
                self._signature = self.fetch_signatures[self.signature_name]
                return self._signature
            except KeyError:
                raise oelite.fetch.NoSignature(self.uri, "signature unknown")
        elif self.branch:
            warnings.warn("fetching git branch head, causing source signature to not be sufficient for proper signature handling")
            return ""
        raise Exception("this should not be reached")

    def get_cache(self):
        try:
            return self.cache
        except AttributeError:
            self.cache = fetching.git_cache.Fetcher(self.url, cache=self.repo,
                                                    remote_name=self.remote)
            return self.cache

    def fetch(self):
        cache = self.get_cache()
        cache.setup_cache()

        fetched = False
        for url in self.uri.premirrors + [self.url] + self.uri.mirrors:
            if self.tag and cache.has_tag(self.tag):
                fetched = True
                break
            if self.commit and cache.has_commit(self.commit):
                fetched = True
                break
            if not isinstance(url, basestring):
                if url[0].endswith("//"):
                    url = os.path.join(url[0].rstrip("/"), self.mirror_name)
                    url += ".git"
                else:
                    url = os.path.join(url[0], url[1])
            try:
                cache.update(url)
            except Exception, e:
                print "Warning: fetching %s failed: %s"%(url, e)
                continue
            fetched = True
            break

        if not fetched and not self.branch:
            print "Error: git fetching failed"
            return False

        if self.tag:
            commit = cache.query_tag(self.tag)
            if not commit:
                raise oelite.fetch.FetchError(self.uri, "unknown tag: %s"%(self.tag))
            if not "_signature" in dir(self):
                return (self.signature_name, commit)
            if (commit != self._signature):
                print "Error signature mismatch "+self.tag
                print "  expected: %s"%self._signature
                print "  obtained: %s"%commit
            return commit == self._signature
        return True

    def unpack(self, d):
        cache = self.get_cache()
        rev = self.commit or self.tag or self.branch
        cache.download(os.path.join(d.get("SRCDIR"), self.dest),
                       rev=rev, force=True)
        return True

    def mirror(self, mirror=os.getcwd()):
        path = os.path.join(self.uri.isubdir, "git", self.mirror_name) + ".git"
        print "Updating git mirror", path
        cache = self.get_cache()
        repo = cache.update_bare_dest(path)
        repo.git.update_server_info()
        return True
