# couchstore.py
# Python interface to CouchStore library

from ctypes import *        # <http://docs.python.org/library/ctypes.html>
import errno

# Load the couchstore library and customize return types:
try:
    _lib = CDLL("libcouchstore.so")         # Linux
except OSError:
    try:
        _lib = CDLL("libcouchstore.dylib")  # Mac OS
    except OSError:
        _lib = CDLL("couchstore")           # Windows (?)

_lib.couchstore_strerror.restype = c_char_p


class CouchStoreException (Exception):
    """Exceptions raised by CouchStore APIs."""
    def __init__ (self, errcode):
        Exception.__init__(self, _lib.couchstore_strerror(errcode))
        self.code = errcode


### INTERNAL FUNCTIONS:

def _check (err):
    if err == 0:
        return
    elif err == -3:
        raise MemoryError()
    elif err == -5:
        raise KeyError()
    elif err == -11:
        raise OSError(errno.ENOENT)
    else:
        raise CouchStoreException(err)


def _toString (key):
    if not isinstance(key, basestring):
        raise TypeError(key)
    return str(key)


### INTERNAL STRUCTS:

class SizedBuf (Structure):
    _fields_ = [("buf", c_char_p), ("size", c_ulonglong)]

    def __init__(self, string):
        if string != None:
            string = _toString(string)
            Structure.__init__(self, string, len(string))
        else:
            Structure.__init__(self, None, 0)

    def __str__(self):
        return string_at(self.buf, self.size)

class DocStruct (Structure):
    _fields_ = [("id", SizedBuf), ("data", SizedBuf)]

class DocInfoStruct (Structure):
    _fields_ = [("id", SizedBuf),
                ("db_seq", c_ulonglong),
                ("rev_seq", c_ulonglong),
                ("rev_meta", SizedBuf),
                ("deleted", c_int),
                ("content_meta", c_ubyte),
                ("bp", c_ulonglong),
                ("size", c_ulonglong) ]


### DOCUMENT INFO CLASS:

class DocumentInfo (object):
    """Metadata of a document in a CouchStore database."""

    @staticmethod
    def _fromStruct (info, store = None):
        self = DocumentInfo()
        self.store = store
        self.id = str(info.id)
        self.sequence = info.db_seq
        self.revSequence = info.rev_seq
        self.revMeta = str(info.rev_meta)
        self.deleted = (info.deleted != 0)
        self.contentMeta = info.content_meta
        self._bp = info.bp
        self.size = info.size
        return self

    def _asStruct(self):
        return DocInfoStruct(SizedBuf(self.id), self.sequence, self.revSequence,
                             SizedBuf(self.revMeta), self.deleted,
                             self.contentMeta, self._bp, self.size)

    def __str__ (self):
        return "DocumentInfo('%s', %d bytes)" % (self.id, self.size)

    def __repr__ (self):
        return "DocumentInfo('%s', %d bytes)" % (self.id, self.size)

    def dump (self):
        return "DocumentInfo('%s', %d bytes, seq=%d, revSeq=%d, deleted=%s, contentMeta=%d, bp=%d)" % \
                 (self.id, self.size, self.sequence, self.revSequence, self.deleted, \
                  self.contentMeta, self._bp)

    def getContents(self, options =0):
        """Fetches and returns the contents of a DocumentInfo returned from CouchStore's getInfo
           or getInfoBySequence methods."""
        if not self.store or not self._bp:
            raise Exception("Contents unknown")
        info = DocInfoStruct()
        info.contentMeta = self.contentMeta
        info.bp = self._bp
        docptr = pointer(DocStruct())
        _lib.couchstore_open_doc_with_docinfo(self.store, byref(info), byref(docptr), options)
        contents = str(docptr.contents.data)
        _lib.couchstore_free_document(docptr)
        return contents


### COUCHSTORE CLASS:

class CouchStore (object):
    """Interface to a CouchStore database."""

    def __init__ (self, path, mode =None):
        """Creates a CouchStore at a given path. The option mode parameter can be 'r' for
           read-only access, or 'c' to create the file if it doesn't already exist."""
        if mode == 'r':
            flags = 2 # RDONLY
        elif mode == 'c':
            flags = 1 # CREATE
        else:
            flags = 0

        db = c_void_p()
        _check(_lib.couchstore_open_db(path, flags, byref(db)))
        self._as_parameter_ = db
        self.path = path

    def __del__(self):
        self.close()

    def close (self):
        """Closes the CouchStore."""
        if hasattr(self, "_as_parameter_"):
            _lib.couchstore_close_db(self)
            del self._as_parameter_

    def __str__(self):
        return "CouchStore(%s)" % self.path

    COMPRESS = 1

    def save (self, id, data, options =0):
        """Saves a document with the given ID. Returns the sequence number."""
        if isinstance(id, DocumentInfo):
            infoStruct = id._asStruct
            idbuf = infoStruct.id
        else:
            idbuf = SizedBuf(id)
            infoStruct = DocInfoStruct(idbuf)
        if data != None:
            doc = DocStruct(idbuf, SizedBuf(data))
            docref = byref(doc)
        else:
            docref = None
        _check(_lib.couchstore_save_document(self, docref, byref(infoStruct), options))
        if isinstance(id, DocumentInfo):
            id.sequence = infoStruct.db_seq
        return infoStruct.db_seq

    def saveMultiple(self, ids, datas, options =0):
        """Saves multiple documents. 'ids' is an array of either strings or DocumentInfo objects.
           'datas' is a parallel array of value strings (or None, in which case the documents
           will be deleted.) Returns an array of new sequence numbers."""
        n = len(ids)
        docStructs = (POINTER(DocStruct) * n)()
        infoStructs = (POINTER(DocInfoStruct) * n)()
        for i in xrange(0, n):
            id = ids[i]
            if isinstance(id, DocumentInfo):
                info = id._asStruct()
            else:
                info = DocInfoStruct(SizedBuf(id))
            doc = DocStruct(info.id)
            if datas and datas[i]:
                doc.data = SizedBuf(datas[i])
            else:
                info.deleted = True
            infoStructs[i] = pointer(info)
            docStructs[i] = pointer(doc)
        _check(_lib.couchstore_save_documents(self, byref(docStructs), byref(infoStructs), n, \
                                              options))
        return [info.contents.db_seq for info in infoStructs]
    pass

    def commit (self):
        """Ensures all saved data is flushed to disk."""
        _check(_lib.couchstore_commit(self))

    DECOMPRESS = 1

    def get (self, id, options =0):
        """Returns the contents of a document (as a string) given its ID."""
        id = _toString(id)
        docptr = pointer(DocStruct())
        err = _lib.couchstore_open_document(self, id, len(id), byref(docptr), options)
        if err == -5:
            raise KeyError(id)
        _check(err)
        data = str(docptr.contents.data)
        _lib.couchstore_free_document(docptr)
        return data

    def __getitem__ (self, key):
        return self.get(key)

    def __setitem__ (self, key, value):
        self.save(key, value)

    def __delitem__ (self, key):
        self.save(key, None)

    # Getting document info:

    def _infoPtrToDoc (self, key, infoptr, err):
        if err == -5:
            raise KeyError(key)
        _check(err)
        info = infoptr.contents
        if info == None:
            return None
        doc = DocumentInfo._fromStruct(info, self)
        _lib.couchstore_free_docinfo(infoptr)
        return doc

    def getInfo (self, id):
        """Returns the DocumentInfo object with the given ID."""
        id = _toString(id)
        infoptr = pointer(DocInfoStruct())
        err = _lib.couchstore_docinfo_by_id(self, id, len(id), byref(infoptr))
        return self._infoPtrToDoc(id, infoptr, err)

    def getInfoBySequence (self, sequence):
        """Returns the DocumentInfo object with the given sequence number."""
        infoptr = pointer(DocInfoStruct())
        err = _lib.couchstore_docinfo_by_sequence(self, c_ulonglong(sequence), byref(infoptr))
        return self._infoPtrToDoc(sequence, infoptr, err)

    # Iterating:

    ITERATORFUNC = CFUNCTYPE(c_int, c_void_p, POINTER(DocInfoStruct), c_void_p)

    def forEachChange(self, since, fn):
        """Calls the function "fn" once for every document sequence since the "since" parameter.
           The single parameter to "fn" will be a DocumentInfo object. You can call
           getContents() on it to get the document contents."""
        def callback (dbPtr, docInfoPtr, context):
            fn(DocumentInfo._fromStruct(docInfoPtr.contents, self))
            return 0
        _check(_lib.couchstore_changes_since(self, since, 0, \
               CouchStore.ITERATORFUNC(callback), c_void_p(0)))

    def changesSince (self, since):
        """Returns an array of DocumentInfo objects, for every document that's changed since the
           sequence number "since"."""
        changes = []
        self.forEachChange(since, lambda docInfo: changes.append(docInfo))
        return changes
