#include <Python.h>
#include <structmember.h>
#include <bytearrayobject.h>

#include <stdio.h>


#define PAGE_SHIFT    8
#define PAGE_SIZE     (1 << PAGE_SHIFT)
#define PAGE_MASK     (~(PAGE_SIZE - 1))


#define LINE_USED     0x01
#define LINE_DIRTY    0x02

#define is_used(_line) ((_line)->cl_flags & LINE_USED)
#define set_used(_line) ((_line)->cl_flags |= LINE_USED)
#define clear_used(_line) ((_line)->cl_flags &= ~LINE_USED)

#define is_dirty(_line) ((_line)->cl_flags & LINE_DIRTY)
#define set_dirty(_line) ((_line)->cl_flags |= LINE_DIRTY)
#define clear_dirty(_line) ((_line)->cl_flags &= ~LINE_DIRTY)

#define touch(_line) do { (_line)->cl_stamp = (_line)->cl_cache->dc_stamp++; } while(0)

#define RETURN_NONE()    do { Py_INCREF(Py_None); return Py_None; } while(0) 
#define BOOL_DEFAULT_FALSE(_o)  ((_o) != NULL ? PyObject_IsTrue(_o) : 0)
#define BOOL_DEFAULT_TRUE(_o)   ((_o) != NULL ? PyObject_IsTrue(_o) : 1)

#define DEBUG(_self, ...) do { sprintf(debug_buff, __VA_ARGS__); PyObject_CallMethod((_self)->dc_core, "DEBUG", "s", debug_buff); } while(0)
//#define DEBUG(_self, ...) do { } while(0)

#define WORD_LB(u16)  ((unsigned char)(u16 & 0xFF))
#define WORD_HB(u16)  ((unsigned char)((u16 >> 8) & 0xFF))
#define WORD(lb, hb)  ((unsigned int)(lb | (hb << 8)))

typedef struct CPUDataCache_s CPUDataCache;

typedef struct {
  unsigned int   cl_index;
  CPUDataCache * cl_cache;

  unsigned int   cl_tag;
  unsigned int   cl_address;
  unsigned int   cl_stamp;
  unsigned char  cl_flags;
  unsigned char* cl_data;
} cache_line_t;

struct CPUDataCache_s {
    PyObject_HEAD

    PyObject *dc_controller;
    PyObject *dc_core;

    unsigned int dc_size;

    unsigned int dc_lines_count;
    unsigned int dc_lines_length;
    unsigned int dc_lines_assoc;

    uint8_t dc_sets;

    unsigned int dc_tag_mask;
    unsigned int dc_tag_shift;
    unsigned int dc_set_mask;
    unsigned int dc_set_shift;
    unsigned int dc_offset_mask;

    unsigned int dc_stamp;

    unsigned char *dc_buffer;
    cache_line_t *dc_lines;

    unsigned int dc_reads;
    unsigned int dc_hits;
    unsigned int dc_misses;
    unsigned int dc_prunes;
    unsigned int dc_forced_writes;
};

static char debug_buff[4096];


static unsigned int fls(unsigned int x)
{
  unsigned int r;

  asm("bsrl %1,%0\n\t"
      "jnz 1f\n\t"
      "movl $-1,%0\n"
      "1:" : "=r" (r) : "rm" (x));

  return r + 1;
}

static void DC_dealloc(CPUDataCache *self)
{
  PyMem_Free(self->dc_lines);
  self->dc_lines = NULL;

  PyMem_Free(self->dc_buffer);
  self->dc_buffer = NULL;

  Py_XDECREF(self->dc_controller);
  self->dc_controller = NULL;

  Py_XDECREF(self->dc_core);
  self->dc_core = NULL;

  self->ob_type->tp_free((PyObject *) self);
}

static PyObject * DC_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
  CPUDataCache *self;

  self = (CPUDataCache *) type->tp_alloc(type, 0);

  if (!self)
    return NULL;

  self->dc_controller = Py_None;
  self->dc_core = Py_None;
  self->dc_size = 0;
  self->dc_lines_count = 0;
  self->dc_lines_length = 0;
  self->dc_stamp = 0;

  self->dc_reads = 0;
  self->dc_hits = 0;
  self->dc_misses = 0;
  self->dc_prunes = 0;
  self->dc_forced_writes = 0;

  Py_INCREF(self->dc_controller);
  Py_INCREF(self->dc_core);

  return (PyObject *) self;
}

static int DC_init(CPUDataCache *self, PyObject *args, PyObject *kwds)
{
  PyObject *controller, *core, *tmp;
  int i;
  cache_line_t *line;

  if (!PyArg_ParseTuple(args, "OOIII", &controller, &core, &self->dc_size, &self->dc_lines_length, &self->dc_lines_assoc))
    return -1;

  self->dc_lines_count = self->dc_size / self->dc_lines_length;

  self->dc_lines = PyMem_Malloc(sizeof(cache_line_t) * self->dc_lines_count);
  if (!self->dc_lines)
    return -1;

  self->dc_buffer = PyMem_Malloc(sizeof(uint8_t) * self->dc_size);
  if (!self->dc_buffer) {
    PyMem_Free(self->dc_lines);
    return -1;
  }

  for(i = 0; i < self->dc_lines_count; i++) {
    line = &self->dc_lines[i];

    line->cl_index = i;
    line->cl_cache = self;

    line->cl_data = self->dc_buffer + i * self->dc_lines_length;

    clear_used(line);
    clear_dirty(line);
  }

  unsigned int offset_length, set_length, tag_length;

  offset_length = ffs(self->dc_lines_length) - 1;
  set_length = ffs(self->dc_lines_count / self->dc_lines_assoc) - 1;
  tag_length = 32 - set_length - offset_length;

  self->dc_offset_mask = self->dc_lines_length - 1;

  self->dc_set_shift = offset_length;
  self->dc_set_mask = ((self->dc_lines_count / self->dc_lines_assoc) - 1) << self->dc_set_shift;

  self->dc_tag_mask = ~((1 << (set_length + offset_length)) - 1);

  if (controller) {
    tmp = self->dc_controller;
    Py_INCREF(controller);
    self->dc_controller = controller;
    Py_XDECREF(tmp);
  }

  if (core) {
    tmp = self->dc_core;
    Py_INCREF(core);
    self->dc_core = core;
    Py_XDECREF(tmp);
  }

  DEBUG(self, "DC: size=%u, line-length=%u, line-count=%u, associativity=%u, sets=%u", self->dc_size, self->dc_lines_length, self->dc_lines_count, self->dc_lines_assoc, self->dc_lines_count / self->dc_lines_assoc);
  DEBUG(self, "DC: offset-length=%u, set-length=%u, tag_length=%u", offset_length, set_length, tag_length);
  DEBUG(self, "DC: offset-mask=0x%08X, set-mask=0x%08X, tag-mask=0x%08X", self->dc_offset_mask, self->dc_set_mask, self->dc_tag_mask);

  return 0;
}


static void DEBUG_LINE(CPUDataCache *self, cache_line_t *line)
{
  static char buff2[4096];
  int i;
  char *ptr = buff2;

  ptr += sprintf(ptr, "    ");
  for (i = 0; i < self->dc_lines_length; i++) {
    ptr += sprintf(ptr, "0x%02X ", line->cl_data[i]);
    if (i == 7 || i == 15 || i == 23)
      ptr += sprintf(ptr, "\n    ");
  }

  DEBUG(self, "DC: line=%p\n%s", line, buff2);
}

static int __get_page_data(CPUDataCache *self, unsigned int address, PyObject **provider, char **buff)
{
  PyObject *mc, *pg, *data;
  int offset = 0;

  DEBUG(self, "DC.__get_page_data: address=0x%06X", address);

  mc = PyObject_GetAttrString(self->dc_core, "memory");
  if (!mc)
    return -1;

  Py_DECREF(mc);

  pg = PyObject_CallMethod(mc, "page", "I", (address & PAGE_MASK) >> PAGE_SHIFT);
  if (!pg)
    return -1;

  Py_DECREF(pg);

  DEBUG(self, "  DC: pg=%s", PyString_AsString(PyObject_Repr(pg)));

  data = PyObject_GetAttrString(pg, "data");
  if (!data)
    return -1;

  Py_DECREF(data);

  if (!data->ob_type || !data->ob_type->tp_as_buffer || !data->ob_type->tp_as_buffer->bf_getreadbuffer) {
    PyErr_SetString(PyExc_RuntimeError, "Data provider does not support buffer protocol");
    return -1;
  }

  if (PyObject_HasAttrString(pg, "offset")) {
    PyObject *o = PyObject_GetAttrString(pg, "offset");
    if (!o)
      return -1;

    offset = PyInt_AsLong(o);
    Py_DECREF(o);
  }

  if (data->ob_type->tp_as_buffer->bf_getreadbuffer(data, 0, (void **)buff) == -1)
    return -1;

  DEBUG(self, "DC.__get_page_data: address=0x%06X, buff=%p, offset=%i", address, *buff, offset);

  *buff = (*buff + offset);
  *provider = data;

  return 0;
}

static int __read_line_from_memory(unsigned int address, cache_line_t *line)
{
  PyObject *provider;
  char *buff;

  DEBUG(line->cl_cache, "DC.__read_line_from_memory: address=0x%06X, line=%i", address, line->cl_index);

  if (__get_page_data(line->cl_cache, address, &provider, &buff))
    return -1;

  memcpy(line->cl_data, &buff[address & (~PAGE_MASK)], sizeof(unsigned char) * line->cl_cache->dc_lines_length);

  line->cl_address = address;
  set_used(line);
  clear_dirty(line);

  DEBUG_LINE(line->cl_cache, line);

  return 0;
}

static int __write_line_to_memory(cache_line_t *line)
{
  PyObject *provider;
  char *buff;

  if (__get_page_data(line->cl_cache, line->cl_address, &provider, &buff))
    return -1;

  memcpy(&buff[line->cl_address & (~PAGE_MASK)], line->cl_data, sizeof(unsigned char) * line->cl_cache->dc_lines_length);

  clear_dirty(line);

  DEBUG(line->cl_cache, "DC.__write_line_to_memory: addrress=0x%06X", line->cl_address);
  DEBUG_LINE(line->cl_cache, line);

  return 0;
}

static cache_line_t *__fill_line(unsigned int address, unsigned int tag, cache_line_t *line)
{
  DEBUG(line->cl_cache, "DC.__fill_line: address=0x%06X, tag=0x%06X, line=%p", address, tag, (void *)line);

  if (__read_line_from_memory(address, line))
    return NULL;

  line->cl_tag = tag;
  touch(line);

  return line;
}

static cache_line_t *__get_line_for_address(CPUDataCache *self, unsigned int address, int fetch)
{
  cache_line_t *line, *first_empty = NULL, *oldest = NULL;
  unsigned int tag, set, way;
  int i;

  DEBUG(self, "DC.__get_line_for_address: address=0x%06X, fetch=%i", address, fetch);

  self->dc_reads += 1;

  address &= ~(self->dc_offset_mask);

  DEBUG(self, "  address=0x%06X", address);

  tag = (address & self->dc_tag_mask);
  set = (address & self->dc_set_mask) >> self->dc_set_shift;

  DEBUG(self, "  tag=0x%06X, set=0x%06X", tag, set);

  for (i = 0; i < self->dc_lines_assoc; i++) {
    line = &self->dc_lines[set * self->dc_lines_assoc + i];

    if (!is_used(line)) {
      if (!first_empty)
        first_empty = line;

      continue;
    }

    if (line->cl_tag != tag)
      continue;

    DEBUG(self, "  line present in cache: index=%i, line=%p", i, (void *)line);

    self->dc_hits += 1;

    touch(line);
    return line;
  }

  /* not in cache */

  /* should we fetch it from main memory? */
  if (!fetch) {
    DEBUG(self, "  asked to avoid loading, quit then");
    return NULL;
  }

  self->dc_misses += 1;

  if (first_empty)
    return __fill_line(address, tag, first_empty);

  DEBUG(self, "  no free line");

  self->dc_prunes += 1;

  for(i = 0; i < self->dc_lines_assoc; i++) {
    line = &self->dc_lines[set * self->dc_lines_assoc + i];

    if (!oldest)
      oldest = line;

    if (line->cl_stamp < oldest->cl_stamp)
      oldest = line;
  }

  if (is_dirty(oldest)) {
    self->dc_forced_writes = 0;

    if (__write_line_to_memory(oldest))
      return NULL;
  }

  return __fill_line(address, tag, oldest);
}

static int __release_line(CPUDataCache *self, cache_line_t *line, int writeback, int remove)
{
  if (!is_used(line))
    return 0;

  if (writeback && is_dirty(line) && __write_line_to_memory(line))
    return -1;

  if (remove)
    clear_used(line);

  return 0;
}

static int __release_entry_reference(CPUDataCache *self, unsigned int address, int writeback, int remove)
{
  cache_line_t *line = __get_line_for_address(self, address, 0);

  if (!line)
    return 0;

  return __release_line(self, line, writeback, remove);
}

static PyObject *DC_read_u8(CPUDataCache *self, PyObject *args)
{
  cache_line_t *line;
  int address, offset;

  if (!PyArg_ParseTuple(args, "I", &address))
    return NULL;

  DEBUG(self, "DC.read_u8: address=0x%06X", address);

  line = __get_line_for_address(self, address, 1);
  if (!line)
    return NULL;

  offset = address & self->dc_offset_mask;

  DEBUG(self, "  DC: address=0x%06X, offset=0x%06X", address, offset);
  DEBUG_LINE(self, line);

  return PyInt_FromLong(line->cl_data[offset]);
}

static PyObject *DC_read_u16(CPUDataCache *self, PyObject *args)
{
  cache_line_t *line;
  int address, offset;

  if (!PyArg_ParseTuple(args, "I", &address))
    return NULL;

  DEBUG(self, "DC.read_u16: address=0x%06X", address);

  line = __get_line_for_address(self, address, 1);
  if (!line)
    return NULL;

  offset = address & self->dc_offset_mask;

  DEBUG(self, "  DC: address=0x%06X, offset=0x%06X", address, offset);
  DEBUG_LINE(self, line);

  return PyInt_FromLong(WORD(line->cl_data[offset], line->cl_data[offset + 1]));
}

static PyObject *DC_write_u8(CPUDataCache *self, PyObject *args)
{
  cache_line_t *line;
  unsigned int address, offset, value;

  if (!PyArg_ParseTuple(args, "II", &address, &value))
    return NULL;

  DEBUG(self, "DC.write_u8: address=0x%06X", address);

  line = __get_line_for_address(self, address, 1);
  if (!line)
    return NULL;

  offset = address & self->dc_offset_mask;

  DEBUG(self, "  DC: address=0x%06X, offset=0x%06X, value=0x%02X", address, offset, value);

  line->cl_data[offset] = WORD_LB(value);
  set_dirty(line);

  RETURN_NONE();
}

static PyObject *DC_write_u16(CPUDataCache *self, PyObject *args)
{
  cache_line_t *line;
  unsigned int address, offset, value;

  if (!PyArg_ParseTuple(args, "II", &address, &value))
    return NULL;

  DEBUG(self, "DC.write_u16: address=0x%06X", address);

  line = __get_line_for_address(self, address, 1);
  if (!line)
    return NULL;

  offset = address & self->dc_offset_mask;

  DEBUG(self, "  DC: address=0x%06X, offset=0x%06X, value=0x%04X (0x%02X, 0x%02X)", address, offset, value, WORD_LB(value), WORD_HB(value));

  line->cl_data[offset]     = WORD_LB(value);
  line->cl_data[offset + 1] = WORD_HB(value);
  set_dirty(line);

  DEBUG_LINE(self, line);

  RETURN_NONE();
}

static PyObject *DC_release_entry_references(CPUDataCache *self, PyObject *args, PyObject *kwargs)
{
  unsigned int address;
  PyObject *writeback = NULL, *remove = NULL;
  static char *kwlist[] = {"address", "writeback", "remove", NULL};

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "I|OO", kwlist, &address, &writeback, &remove))
    return NULL;

  if (__release_entry_reference(self, address, BOOL_DEFAULT_TRUE(writeback), BOOL_DEFAULT_TRUE(remove)))
    return NULL;

  RETURN_NONE();
}

static PyObject *DC_release_page_references(CPUDataCache *self, PyObject *args, PyObject *kwargs)
{
  unsigned int address, i;
  PyObject *page, *writeback = NULL, *remove = NULL, *base_address;
  static char *kwlist[] = {"page", "writeback", "remove", NULL};

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", kwlist, &page, &writeback, &remove))
    return NULL;

  base_address = PyObject_GetAttrString(page, "base_address");
  if (!base_address)
    return NULL;

  address = PyInt_AsLong(base_address);
  Py_DECREF(base_address);

  DEBUG(self, "DC.release_page_references: page=%i, address=0x%06X", (int)PyInt_AsLong(PyObject_GetAttrString(page, "index")), address);

  for (i = address; i < address + PAGE_SIZE; i += self->dc_lines_length) {
    if (__release_entry_reference(self, i, BOOL_DEFAULT_TRUE(writeback), BOOL_DEFAULT_TRUE(remove)))
      return NULL;
  }

  RETURN_NONE();
}

static PyObject *DC_release_area_references(CPUDataCache *self, PyObject *args, PyObject *kwargs)
{
  unsigned int address, i, size;
  PyObject *writeback = NULL, *remove = NULL;
  static char *kwlist[] = {"address", "size", "writeback", "remove", NULL};

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "II|OO", kwlist, &address, &size, &writeback, &remove))
    return NULL;

  DEBUG(self, "DC.release_area_references: start=0x%06X, size=%u", address, size);

  for(i = address; i < address + size; i += self->dc_lines_length)
    if (__release_entry_reference(self, i, BOOL_DEFAULT_TRUE(writeback), BOOL_DEFAULT_TRUE(remove)))
      return NULL;

  RETURN_NONE();
}

static PyObject *DC_release_references(CPUDataCache *self, PyObject *args, PyObject *kwargs)
{
  PyObject *writeback = NULL, *remove = NULL;
  static char *kwlist[] = {"writeback", "remove", NULL};
  int i;

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|OO", kwlist, &writeback, &remove))
    return NULL;

  DEBUG(self, "DC.release_references: writeback=%i, remove=%i", BOOL_DEFAULT_TRUE(writeback), BOOL_DEFAULT_TRUE(remove));

  for(i = 0; i < self->dc_lines_count; i++)
    if (__release_line(self, &self->dc_lines[i], BOOL_DEFAULT_TRUE(writeback), BOOL_DEFAULT_TRUE(remove)))
      return NULL;

  RETURN_NONE();
}

static PyObject *DC_clear(CPUDataCache *self)
{
  int i;

  for(i = 0; i < self->dc_lines_count; i++)
    if (__release_line(self, &self->dc_lines[i], 0, 1))
      return NULL;

  RETURN_NONE();
}

static PyObject *DC_repr(CPUDataCache *self)
{
  return PyString_FromFormat("L1 cache: %u size, %u line length with %u-way assoc", self->dc_size, self->dc_lines_length, self->dc_lines_assoc);
}

static PyMemberDef DC_members[] = {
    {"controller", T_OBJECT_EX, offsetof(CPUDataCache, dc_controller), 0, "controller"},
    {"core", T_OBJECT_EX, offsetof(CPUDataCache, dc_core), 0, "core"},

    {"size",         T_INT, offsetof(CPUDataCache, dc_size),         0, "size"},
    {"lines_count", T_INT, offsetof(CPUDataCache, dc_lines_count), 0, "number of lines"},
    {"lines_length", T_INT, offsetof(CPUDataCache, dc_lines_length), 0, "line size"},
    {"lines_assoc",  T_INT, offsetof(CPUDataCache, dc_lines_assoc),  0, "lines assoc"},

    {"reads",  T_INT, offsetof(CPUDataCache, dc_reads),  0, "number of reads"},
    {"hits",   T_INT, offsetof(CPUDataCache, dc_hits),   0, "number of hits"},
    {"misses", T_INT, offsetof(CPUDataCache, dc_misses), 0, "number of misses"},
    {"prunes", T_INT, offsetof(CPUDataCache, dc_prunes), 0, "number of prunes"},
    {"forced_writes", T_INT, offsetof(CPUDataCache, dc_forced_writes), 0, "number of forced writes"},

    {NULL}  /* Sentinel */
};

static PyMethodDef DC_methods[] = {
  {"read_u8",   (PyCFunction) DC_read_u8,   METH_VARARGS, ""},
  {"read_u16",  (PyCFunction) DC_read_u16,  METH_VARARGS, ""},
  {"write_u8",  (PyCFunction) DC_write_u8,  METH_VARARGS, ""},
  {"write_u16", (PyCFunction) DC_write_u16, METH_VARARGS, ""},
  {"release_entry_references", (PyCFunction) DC_release_entry_references, METH_VARARGS | METH_KEYWORDS, ""},
  {"release_page_references", (PyCFunction) DC_release_page_references, METH_VARARGS | METH_KEYWORDS, ""},
  {"release_area_references", (PyCFunction) DC_release_area_references, METH_VARARGS | METH_KEYWORDS, ""},
  {"release_references", (PyCFunction) DC_release_references, METH_VARARGS | METH_KEYWORDS, ""},
  {"clear",                   (PyCFunction) DC_clear,         METH_NOARGS,                       ""},
  {NULL}
};

static PyTypeObject CPUDataCacheType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "ducky.native.CPUDataCache",             /*tp_name*/
    sizeof(CPUDataCache),             /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)DC_dealloc, /*tp_dealloc*/
    0,                         /*tp_print*/
    0,                         /*tp_getattr*/
    0,                         /*tp_setattr*/
    0,                         /*tp_compare*/
    (reprfunc)DC_repr,         /*tp_repr*/
    0,                         /*tp_as_number*/
    0,                         /*tp_as_sequence*/
    0,                         /*tp_as_mapping*/
    0,                         /*tp_hash */
    0,                         /*tp_call*/
    0,                         /*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
    "CPU Data Cache - native implementation",           /* tp_doc */
    0,		               /* tp_traverse */
    0,		               /* tp_clear */
    0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    0,		               /* tp_iter */
    0,		               /* tp_iternext */
    DC_methods,             /* tp_methods */
    DC_members,             /* tp_members */
    0,                         /* tp_getset */
    0,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    (initproc)DC_init,      /* tp_init */
    0,                         /* tp_alloc */
    DC_new,                 /* tp_new */
};

static PyMethodDef module_methods[] = {
    {NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC initdata_cache(void)
{
  PyObject* m;

  if (PyType_Ready(&CPUDataCacheType) < 0)
    return;

  m = Py_InitModule3("data_cache", module_methods, "");

  if (m == NULL)
    return;

  Py_INCREF(&CPUDataCacheType);
  PyModule_AddObject(m, "CPUDataCache", (PyObject *)&CPUDataCacheType);
}
