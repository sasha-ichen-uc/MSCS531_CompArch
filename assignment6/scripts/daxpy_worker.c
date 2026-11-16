/*
 * DAXPY worker for gem5 SE mode multi-process TLP simulation.
 * y[i] = a * x[i] + y[i]
 *
 * Each process handles a contiguous portion of the array based on
 * its worker_id and total_workers. Uses deterministic initialization
 * so all workers agree on the data.
 *
 * Usage: ./daxpy_worker <worker_id> <total_workers> <array_size>
 *
 * Compile: zig cc -target x86_64-linux-musl -static -O2 -o daxpy_worker daxpy_worker.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define DEFAULT_SIZE 1024

int main(int argc, char *argv[]) {
    int worker_id = 0;
    int total_workers = 1;
    int array_size = DEFAULT_SIZE;

    if (argc >= 2) worker_id = atoi(argv[1]);
    if (argc >= 3) total_workers = atoi(argv[2]);
    if (argc >= 4) array_size = atoi(argv[3]);

    if (total_workers < 1) total_workers = 1;
    if (worker_id < 0 || worker_id >= total_workers) worker_id = 0;
    if (array_size < 1) array_size = DEFAULT_SIZE;

    double A = 2.5;

    int chunk = array_size / total_workers;
    int remainder = array_size % total_workers;
    int start = worker_id * chunk + (worker_id < remainder ? worker_id : remainder);
    int end = start + chunk + (worker_id < remainder ? 1 : 0);
    int local_size = end - start;

    double *X = (double *)malloc(local_size * sizeof(double));
    double *Y = (double *)malloc(local_size * sizeof(double));
    if (!X || !Y) {
        printf("Worker %d: alloc failed\n", worker_id);
        return 1;
    }

    for (int i = 0; i < local_size; i++) {
        int gi = start + i;
        X[i] = (double)(gi % 100) / 50.0;
        Y[i] = (double)(gi % 73) / 37.0;
    }

    printf("Worker %d/%d: DAXPY a=%.1f, range=[%d,%d), size=%d\n",
           worker_id, total_workers, A, start, end, array_size);

    for (int i = 0; i < local_size; i++) {
        Y[i] = A * X[i] + Y[i];
    }

    int errors = 0;
    for (int i = 0; i < local_size; i++) {
        int gi = start + i;
        double expected = A * ((double)(gi % 100) / 50.0) + ((double)(gi % 73) / 37.0);
        if (fabs(Y[i] - expected) > 1e-10) {
            errors++;
            if (errors <= 3)
                printf("Worker %d: ERROR at %d: expected %.6f got %.6f\n",
                       worker_id, gi, expected, Y[i]);
        }
    }

    if (errors == 0)
        printf("Worker %d: PASSED (%d elements)\n", worker_id, local_size);
    else
        printf("Worker %d: FAILED %d errors\n", worker_id, errors);

    free(X);
    free(Y);
    return errors ? 1 : 0;
}
