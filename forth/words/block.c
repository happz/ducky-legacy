#include <arch/bio.h>
#include "forth.h"

/*
 * Because of using a single u32_t for assigned/dirty bitmaps,
 * maximal size of block cache is 32.
 */
#if CONFIG_BLOCK_CACHE_SIZE > 32
#  error Maximal size of block cache is 32.
#endif


/*
 * This structure represents one block of data on a mass storage device,
 * and ties together such block and memory region called "block buffer".
 */
typedef struct {
  // If set, represents block of this ID
  u32_t  b_id;
  // Once allocated, points to a block buffer for the block
  u8_t * b_buffer;
} block_t;


// Possible error codes in case BIO operation failed.
enum {
  BIO_ERR_SRST    = -1,
  BIO_ERR_STORAGE = -2,
  BIO_ERR_BLOCK   = -3,
  BIO_ERR_COUNT   = -4,
  BIO_ERR_BUFFER  = -5,
  BIO_ERR_RESULT  = -6
};


// Internal block cache
static block_t blocks[CONFIG_BLOCK_CACHE_SIZE];
static u32_t assigned_blocks = 0;
static u32_t dirty_blocks = 0;

#define BLOCK_MASK(index)              (1 << (index))

#define set_assigned(index)            (assigned_blocks |= BLOCK_MASK(index))
#define clear_assigned(index)          (assigned_blocks &= ~BLOCK_MASK(index))

#define set_dirty(index)               (dirty_blocks |= BLOCK_MASK(index))
#define clear_dirty(index)             (dirty_blocks &= ~BLOCK_MASK(index))

// "Current" block is the block most recently accessed by BLOCK, BUFFER,
// LOAD, LIST, or THRU.
static block_t *current_block = NULL;

#define CURRENT_BLOCK_INDEX()          (current_block - &blocks[0])

// Block can serve as input sources, prepare input descriptors for that goal
static input_desc_t load_stack[INPUT_STACK_DEPTH];
static int load_stack_index = 0;

ASM_INT(u32_t, var_SCR);

#if DEBUG_BLOCKS
static void DEBUG_print_block(block_t *block) __attribute__((noinline))
{
  int i, j;
  u8_t *c = block->b_buffer;

  printf("block: id=%u, buffer=0x%08X\r\n", block->b_id, (u32_t)block->b_buffer);

  for(i = 0; i < 32; i++) {
    for(j = 0; j < 32; j++)
      printf("0x%02X ", *c++);
    BR();
  }
  BR();
}
#else
#  define DEBUG_print_block(block) do { } while(0)
#endif

/**
 * Submit one BIO operation to the BIO controller, wait for the operation
 * to finish, and check for possible errors.
 */
static void submit_bio_op(u32_t op, u32_t storage, u32_t block, u32_t count, void *buffer)
{
#define check_status(_fail_code) do { status = *bio_status; if (status & BIO_ERR) __ERR_bio_fail(storage, block, status, _fail_code); } while(0)

  volatile u32_t *bio_status = (volatile u32_t *)(CONFIG_BIO_MMIO_BASE + BIO_MMIO_STATUS);
  u32_t status;

  DEBUG_printf("submit_bio_op: op=%u, storage=%u, block=%u, count=%u, buffer=0x%08X\r\n", op, storage, block, count, buffer);

  // Reset storage state
  *bio_status = BIO_SRST;
  check_status(BIO_ERR_SRST);

  // Setup operation
  *(volatile u32_t *)(CONFIG_BIO_MMIO_BASE + BIO_MMIO_SID)   = 1; // hardcoded storage id
  check_status(BIO_ERR_STORAGE);

  *(volatile u32_t *)(CONFIG_BIO_MMIO_BASE + BIO_MMIO_BLOCK) = block - 1; // in FORTH word, id of the first block is 1
  check_status(BIO_ERR_BLOCK);

  *(volatile u32_t *)(CONFIG_BIO_MMIO_BASE + BIO_MMIO_COUNT) = 1;
  check_status(BIO_ERR_COUNT);

  *(volatile u32_t *)(CONFIG_BIO_MMIO_BASE + BIO_MMIO_ADDR)  = (u32_t)buffer;
  check_status(BIO_ERR_BUFFER);

  *bio_status = (BIO_DMA | op);

  while (1) {
    status = *bio_status;

    if ((status & BIO_RDY || status & BIO_ERR) && !(status & BIO_BUSY))
      break;
  }

  check_status(BIO_ERR_RESULT);
}

/**
 * Read one block from the storage into its assigned block buffer. block_t
 * instance is expected to carry valid ID, and pointer to the block buffer.
 * Data in the buffer will be overwritten.
 */
static void block_read(block_t *block)
{
  DEBUG_printf("block_read: id=%u, buffer=0x%08X\r\n", block->b_id, block->b_buffer);

  submit_bio_op(BIO_READ, CONFIG_BLOCK_STORAGE, block->b_id, 1, block->b_buffer);

  DEBUG_printf("  block read finished\r\n");
}

/**
 * Write data from a block buffer back to the storage. block_t instance is
 * expected to carry valid block ID, and pointer to the block buffer.
 */
static void block_write(block_t *block)
{
  DEBUG_printf("block_write: id=%u, buffer=0x%08X\r\n", block->b_id, block->b_buffer);

  submit_bio_op(BIO_WRITE, CONFIG_BLOCK_STORAGE, block->b_id, 1, block->b_buffer);

  DEBUG_printf("  block write finished\r\n");
}

/**
 * Get block for specified block ID. If requested, load its content
 * into a block buffer.
 */
static block_t *get_block(u32_t bid, int load_content)
{
  DEBUG_printf("get_block: bid=%u, load_content=%d\r\n", bid, load_content);

  int i;
  block_t *block;
  u32_t mask;

  // First, try to find the block already assigned to this ID.
  for (i = 0, mask = 1; i < CONFIG_BLOCK_CACHE_SIZE; i++, mask <<= 1) {
    if (!(assigned_blocks & mask) || blocks[i].b_id != bid)
      continue;

    DEBUG_printf("get_block: found in cache #%d\r\n", i);
    return &blocks[i];
  }

  // Ok, so such block is not in the cache, try to acquire one block for it.
  // First, try to find a free block in the cache.
  DEBUG_printf("get_block: looking for free block\r\n");
  for (i = 0, mask = 1, block = NULL; i < CONFIG_BLOCK_CACHE_SIZE; i++, mask <<= 1) {
    if (assigned_blocks & mask)
      continue;

    DEBUG_printf("get_block: grabing block #%d\r\n", i);

    block = &blocks[i];
    break;
  }

  // If all blocks are assigned, we have to a free one.
  if (!block) {
    // Find first clean assigned block, and unassign it.
    DEBUG_printf("get_block: looking for clean assigned block\r\n");
    for(i = 0, mask = 1, block = NULL; i < CONFIG_BLOCK_CACHE_SIZE; i++, mask <<= 1) {
      if (dirty_blocks & mask)
        continue;

      DEBUG_printf("get_block: grabing block #%d\r\n", i);

      block = &blocks[i];
      clear_assigned(i);
      break;
    }

    // And if even now we don't have a block - because all blocks were
    // dirty - simply free the first block in cache.
    if (!block) {
      DEBUG_printf("get_block: grabing and freeing the first block\r\n");
      DEBUG_printf("get_block: grabing block #0\r\n");

      i = 0;  // it will be needed later for assignment
      block = &blocks[0];

      block_write(block);
      clear_dirty(0);
      clear_assigned(0);
    }
  }

  // Now assign the block to a requested id.
  block->b_id = bid;
  set_assigned(i);

  if (!block->b_buffer)
    block->b_buffer = malloc(BIO_BLOCK_SIZE);

  if (load_content)
    block_read(block);

  return block;
}

void *do_BLK()
{
  return &current_input->id_blk;
}

void *do_BLOCK(u32_t bid)
{
  DEBUG_printf("do_BLOCK: bid=%u\r\n", bid);

  current_block = get_block(bid, 1);

  DEBUG_printf("  assigned buffer: ");
  DEBUG_print_block(current_block);

  return current_block->b_buffer;
}

void *do_BUFFER(u32_t bid)
{
  DEBUG_printf("do_BUFFER: bid=%u\r\n", bid);

  current_block = get_block(bid, 0);

  DEBUG_printf("  assigned buffer: ");
  DEBUG_print_block(current_block);

  return current_block->b_buffer;
}

void do_EMPTY_BUFFERS()
{
  DEBUG_printf("do_EMPTY_BUFFERS:\r\n");

  assigned_blocks = 0;
  dirty_blocks = 0;
  current_block = NULL;
}

void do_FLUSH()
{
  DEBUG_printf("do_FLUSH:\r\n");

  do_SAVE_BUFFERS();

  assigned_blocks = 0;
  current_block = NULL;

  DEBUG_printf("do_FLUSH: all buffers unassigned\r\n");
}

void do_LIST(u32_t bid)
{
  char *s = do_BLOCK(bid);
  int i;

  if (dirty_blocks & (1 << CURRENT_BLOCK_INDEX())) {
    printf("Screen %u modified\r\n", bid);
  } else {
    printf("Screen %u not modified\r\n", bid);
  }

  for(i = 0; i < CONFIG_LIST_LPS; i++) {
    printf("%02d ", i);
    puts(s, CONFIG_LIST_CPL); BR();

    s += CONFIG_LIST_CPL;
  }

  var_SCR = current_block->b_id;
}

void do_SAVE_BUFFERS()
{
  DEBUG_printf("do_SAVE_BUFFERS:\r\n");

  int i;
  u32_t mask;

  for(i = 0, mask = 1; i < CONFIG_BLOCK_CACHE_SIZE; i++, mask <<= 1) {
    if (!(assigned_blocks & mask))
      continue;

    if (!(dirty_blocks & mask))
      continue;

    DEBUG_print_block(&blocks[i]);
    block_write(&blocks[i]);
  }

  dirty_blocks = 0;

  DEBUG_printf("do_SAVE_BUFFERS: all buffers clean\r\n");
}

void do_UPDATE()
{
  DEBUG_printf("do_UPDATE:\r\n");

  if (current_block == NULL)
    return;

  set_dirty(CURRENT_BLOCK_INDEX());

  DEBUG_printf("  current buffer:\r\n");
  DEBUG_print_block(current_block);
}

static input_refiller_status_t __load_refiller(input_desc_t *input)
{
  load_stack_index--;
  return EMPTY;
}

void do_BLK_LOAD(u32_t bid)
{
  DEBUG_printf("do_BLK_LOAD: bid=%u\n", bid);

  if (load_stack_index == INPUT_STACK_DEPTH)
    __ERR_input_stack_overflow();

  current_block = get_block(bid, 1);
  input_desc_t *input = &load_stack[load_stack_index++];

  DEBUG_printf("do_BLK_LOAD: assigned block\r\n");
  DEBUG_print_block(current_block);

  input->id_source_id = bid;
  input->id_refiller = __load_refiller;
  input->id_buffer = (char *)current_block->b_buffer;
  input->id_length = BIO_BLOCK_SIZE;
  input->id_index = 0;
  input->id_max_length = BIO_BLOCK_SIZE;
  input->id_blk = bid;

  input_stack_push(input);
}

void do_THRU(u32_t u1, u32_t u2)
{
  for(; u2 >= u1; u2--)
    do_BLK_LOAD(u2);
}
