/* Fast full-frame RGB565 copy for the legacy framebuffer presenter. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>

static PyObject *copy_full(PyObject *self, PyObject *args) {
    PyObject *source_object;
    PyObject *destination_object;
    Py_ssize_t offset;
    Py_ssize_t count;
    Py_buffer source = {0};
    Py_buffer destination = {0};

    if (!PyArg_ParseTuple(args, "OOnn", &source_object, &destination_object, &offset, &count)) {
        return NULL;
    }
    if (offset < 0 || count < 0) {
        PyErr_SetString(PyExc_ValueError, "offset and count must be non-negative");
        return NULL;
    }
    if (PyObject_GetBuffer(source_object, &source, PyBUF_CONTIG_RO) < 0) {
        return NULL;
    }
    if (PyObject_GetBuffer(destination_object, &destination, PyBUF_CONTIG | PyBUF_WRITABLE) < 0) {
        PyBuffer_Release(&source);
        return NULL;
    }
    if (count > source.len || offset > destination.len || count > destination.len - offset) {
        PyBuffer_Release(&destination);
        PyBuffer_Release(&source);
        PyErr_SetString(PyExc_ValueError, "copy range exceeds source or destination buffer");
        return NULL;
    }
    memcpy((char *)destination.buf + offset, source.buf, (size_t)count);
    PyBuffer_Release(&destination);
    PyBuffer_Release(&source);
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"copy_full", copy_full, METH_VARARGS, "Copy a contiguous source buffer directly into a destination buffer."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_fbcopy", NULL, -1, methods,
};

PyMODINIT_FUNC PyInit__fbcopy(void) {
    return PyModule_Create(&module);
}
