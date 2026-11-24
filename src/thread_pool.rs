use crate::Result;
use crate::clock::{monotonic_ns, thread_cpu_time_ns};
use crate::config::WorkloadConfig;
use crate::metrics::ServerCounters;
use crate::protocol::{Outcome, RequestWire, ResponseWire};
use crate::queue::BoundedQueue;
use crate::workload;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::Sender;
use std::thread::{self, JoinHandle};

#[derive(Debug)]
pub struct Task {
    pub request: RequestWire,
    pub server_receive_ns: u64,
    pub admission_ns: u64,
    pub queue_len_at_admission: usize,
}

pub struct ThreadPool {
    handles: Vec<JoinHandle<()>>,
}

impl ThreadPool {
    pub fn start(
        workers: usize,
        queue: Arc<BoundedQueue<Task>>,
        workload_config: WorkloadConfig,
        responses: Sender<ResponseWire>,
        counters: Arc<ServerCounters>,
        drain_deadline_ns: Arc<AtomicU64>,
    ) -> Result<Self> {
        let mut handles = Vec::with_capacity(workers);
        for worker_id in 0..workers {
            let worker_queue = Arc::clone(&queue);
            let worker_responses = responses.clone();
            let worker_counters = Arc::clone(&counters);
            let config = workload_config.clone();
            let worker_drain_deadline = Arc::clone(&drain_deadline_ns);
            let handle = thread::Builder::new()
                .name(format!("cpuquota-worker-{worker_id}"))
                .spawn(move || {
                    while let Some(task) = worker_queue.pop() {
                        let start = monotonic_ns().expect("monotonic clock failed");
                        if start >= worker_drain_deadline.load(Ordering::Acquire) {
                            worker_counters.incomplete_drain_timeout();
                            let response = ResponseWire {
                                request_id: task.request.request_id,
                                outcome: Outcome::Incomplete,
                                server_receive_ns: task.server_receive_ns,
                                admission_ns: Some(task.admission_ns),
                                execution_start_ns: None,
                                completion_ns: Some(start),
                                execution_cpu_ns: None,
                                worker_id: None,
                                checksum: None,
                                queue_len_at_admission: task.queue_len_at_admission,
                                error: Some("server drain deadline elapsed".to_owned()),
                            };
                            if worker_responses.send(response).is_err() {
                                break;
                            }
                            continue;
                        }
                        let iterations = config.iterations_for(task.request.class);
                        let cpu_start = thread_cpu_time_ns().expect("thread CPU clock failed");
                        let checksum = workload::compute(
                            task.request.seed,
                            task.request.request_id,
                            iterations,
                        );
                        let cpu_end = thread_cpu_time_ns().expect("thread CPU clock failed");
                        let completion = monotonic_ns().expect("monotonic clock failed");
                        worker_counters.completed(checksum);
                        let response = ResponseWire {
                            request_id: task.request.request_id,
                            outcome: Outcome::Completed,
                            server_receive_ns: task.server_receive_ns,
                            admission_ns: Some(task.admission_ns),
                            execution_start_ns: Some(start),
                            completion_ns: Some(completion),
                            execution_cpu_ns: Some(cpu_end.saturating_sub(cpu_start)),
                            worker_id: Some(worker_id),
                            checksum: Some(checksum),
                            queue_len_at_admission: task.queue_len_at_admission,
                            error: None,
                        };
                        if worker_responses.send(response).is_err() {
                            break;
                        }
                    }
                })?;
            handles.push(handle);
        }
        Ok(Self { handles })
    }

    pub fn join(self) -> Result<()> {
        for handle in self.handles {
            handle.join().map_err(|_| "worker thread panicked")?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{Phase, TaskClass};
    use std::sync::mpsc;

    #[test]
    fn pool_executes_and_accounts_for_every_task() {
        let queue = Arc::new(BoundedQueue::new(8));
        let (tx, rx) = mpsc::channel();
        let counters = Arc::new(ServerCounters::default());
        let pool = ThreadPool::start(
            2,
            Arc::clone(&queue),
            WorkloadConfig {
                short_iterations: 10,
                long_iterations: 20,
                uniform_iterations: 15,
            },
            tx,
            Arc::clone(&counters),
            Arc::new(AtomicU64::new(u64::MAX)),
        )
        .unwrap();
        for request_id in 0..4 {
            queue
                .try_push(Task {
                    request: RequestWire {
                        request_id,
                        sequence_index: request_id,
                        phase: Phase::Measurement,
                        class: TaskClass::Uniform,
                        seed: 1,
                        intended_arrival_ns: 1,
                        scheduler_emit_ns: 1,
                    },
                    server_receive_ns: 2,
                    admission_ns: 3,
                    queue_len_at_admission: 0,
                })
                .unwrap();
        }
        queue.close();
        pool.join().unwrap();
        let responses: Vec<_> = rx.try_iter().collect();
        assert_eq!(responses.len(), 4);
        assert_eq!(counters.snapshot().completed, 4);
        assert!(
            responses
                .iter()
                .all(|r| r.completion_ns.unwrap() >= r.execution_start_ns.unwrap())
        );
    }

    #[test]
    fn drain_deadline_marks_waiting_tasks_incomplete() {
        let queue = Arc::new(BoundedQueue::new(2));
        queue
            .try_push(Task {
                request: RequestWire {
                    request_id: 1,
                    sequence_index: 0,
                    phase: Phase::Measurement,
                    class: TaskClass::Uniform,
                    seed: 1,
                    intended_arrival_ns: 1,
                    scheduler_emit_ns: 1,
                },
                server_receive_ns: 2,
                admission_ns: 3,
                queue_len_at_admission: 1,
            })
            .unwrap();
        queue.close();
        let (tx, rx) = mpsc::channel();
        let counters = Arc::new(ServerCounters::default());
        let pool = ThreadPool::start(
            1,
            queue,
            WorkloadConfig {
                short_iterations: 10,
                long_iterations: 20,
                uniform_iterations: 15,
            },
            tx,
            Arc::clone(&counters),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        pool.join().unwrap();
        let response = rx.recv().unwrap();
        assert_eq!(response.outcome, Outcome::Incomplete);
        assert_eq!(counters.snapshot().incomplete_drain_timeout, 1);
    }
}
