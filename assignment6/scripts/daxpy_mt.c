/*
 * Multi-threaded DAXPY kernel for gem5 SE mode simulation.
 * y[i] = a * x[i] + y[i]
 *
 * Uses clone() directly for SE-mode compatibility.
 *
 * Usage: ./daxpy_mt [num_threads] [array_size]
 *   defaults: threads=1, array_size=1024
 *
 * Compile: zig cc -target x86_64-linux-musl -static -O2 -o daxpy_mt daxpy_mt.c
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <math.h>

#define DEFAULT_SIZE 1024
#define STACK_SIZE (1024 * 1024)

static double *X;
static double *Y;
static double A = 2.5;
static int ARRAY_SIZE;
static int NUM_THREADS;
static volatile int *barrier_count;
static volatile int *done_flags;

typedef struct {
    int tid;
    int start;
    int end;
} worker_arg_t;

static worker_arg_t *worker_args;

static int daxpy_worker(void *arg) {
    worker_arg_t *w = (worker_arg_t *)arg;
    for (int i = w->start; i < w->end; i++) {
        Y[i] = A * X[i] + Y[i];
    }
    done_flags[w->tid] = 1;
    return 0;
}

int main(int argc, char *argv[]) {
    NUM_THREADS = 1;
    ARRAY_SIZE = DEFAULT_SIZE;

    if (argc >= 2) NUM_THREADS = atoi(argv[1]);
    if (argc >= 3) ARRAY_SIZE = atoi(argv[2]);

    if (NUM_THREADS < 1) NUM_THREADS = 1;
    if (ARRAY_SIZE < 1) ARRAY_SIZE = DEFAULT_SIZE;

    X = (double *)malloc(ARRAY_SIZE * sizeof(double));
    Y = (double *)malloc(ARRAY_SIZE * sizeof(double));
    done_flags = (volatile int *)calloc(NUM_THREADS, sizeof(int));
    barrier_count = (volatile int *)calloc(1, sizeof(int));
    worker_args = (worker_arg_t *)malloc(NUM_THREADS * sizeof(worker_arg_t));

    if (!X || !Y || !done_flags || !barrier_count || !worker_args) {
        write(2, "alloc failed\n", 13);
        return 1;
    }

    for (int i = 0; i < ARRAY_SIZE; i++) {
        X[i] = (double)(i % 100) / 50.0;
        Y[i] = (double)(i % 73) / 37.0;
    }

    printf("DAXPY: a=%.1f, size=%d, threads=%d\n", A, ARRAY_SIZE, NUM_THREADS);

    int chunk = ARRAY_SIZE / NUM_THREADS;
    int remainder = ARRAY_SIZE % NUM_THREADS;

    for (int i = 0; i < NUM_THREADS; i++) {
        worker_args[i].tid = i;
        worker_args[i].start = i * chunk + (i < remainder ? i : remainder);
        worker_args[i].end = worker_args[i].start + chunk + (i < remainder ? 1 : 0);
    }

    for (int i = 1; i < NUM_THREADS; i++) {
        void *stack = mmap(NULL, STACK_SIZE, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK, -1, 0);
        if (stack == MAP_FAILED) {
            printf("mmap failed for thread %d\n", i);
            return 1;
        }
        void *stack_top = (char *)stack + STACK_SIZE;

        int flags = CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND
                    | CLONE_THREAD | CLONE_SYSVSEM;

        long ret = syscall(SYS_clone, flags, stack_top, NULL, NULL, 0);
        if (ret == 0) {
            daxpy_worker(&worker_args[i]);
            syscall(SYS_exit, 0);
        } else if (ret < 0) {
            printf("clone failed for thread %d\n", i);
            return 1;
        }
    }

    daxpy_worker(&worker_args[0]);

    if (NUM_THREADS > 1) {
        for (int i = 1; i < NUM_THREADS; i++) {
            while (!done_flags[i]) {
                sched_yield();
            }
        }
    }

    int errors = 0;
    for (int i = 0; i < ARRAY_SIZE; i++) {
        double expected = A * ((double)(i % 100) / 50.0) + ((double)(i % 73) / 37.0);
        if (fabs(Y[i] - expected) > 1e-10) {
            errors++;
            if (errors <= 5)
                printf("ERROR at %d: expected %.6f got %.6f\n", i, expected, Y[i]);
        }
    }

    if (errors == 0)
        printf("Validation PASSED\n");
    else
        printf("Validation FAILED: %d errors\n", errors);

    return errors ? 1 : 0;
}
