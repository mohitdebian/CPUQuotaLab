use std::collections::VecDeque;
use std::sync::{Condvar, Mutex};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PushError {
    Full,
    Closed,
}

#[derive(Debug)]
pub enum PushWithError<E> {
    Queue(PushError),
    Build(E),
}

struct State<T> {
    items: VecDeque<T>,
    closed: bool,
}

/// A bounded multi-producer, multi-consumer FIFO with nonblocking admission.
pub struct BoundedQueue<T> {
    capacity: usize,
    state: Mutex<State<T>>,
    not_empty: Condvar,
}

impl<T> BoundedQueue<T> {
    #[must_use]
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "queue capacity must be positive");
        Self {
            capacity,
            state: Mutex::new(State {
                items: VecDeque::with_capacity(capacity),
                closed: false,
            }),
            not_empty: Condvar::new(),
        }
    }

    pub fn try_push(&self, value: T) -> std::result::Result<usize, (PushError, T)> {
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        if state.closed {
            return Err((PushError::Closed, value));
        }
        if state.items.len() >= self.capacity {
            return Err((PushError::Full, value));
        }
        state.items.push_back(value);
        let len = state.items.len();
        self.not_empty.notify_one();
        Ok(len)
    }

    pub fn try_push_with<F>(&self, build: F) -> std::result::Result<usize, PushError>
    where
        F: FnOnce(usize) -> T,
    {
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        if state.closed {
            return Err(PushError::Closed);
        }
        if state.items.len() >= self.capacity {
            return Err(PushError::Full);
        }
        let len = state.items.len() + 1;
        state.items.push_back(build(len));
        self.not_empty.notify_one();
        Ok(len)
    }

    pub fn try_push_with_result<F, E>(
        &self,
        build: F,
    ) -> std::result::Result<usize, PushWithError<E>>
    where
        F: FnOnce(usize) -> std::result::Result<T, E>,
    {
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        if state.closed {
            return Err(PushWithError::Queue(PushError::Closed));
        }
        if state.items.len() >= self.capacity {
            return Err(PushWithError::Queue(PushError::Full));
        }
        let len = state.items.len() + 1;
        let value = build(len).map_err(PushWithError::Build)?;
        state.items.push_back(value);
        self.not_empty.notify_one();
        Ok(len)
    }

    pub fn pop(&self) -> Option<T> {
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            if let Some(value) = state.items.pop_front() {
                return Some(value);
            }
            if state.closed {
                return None;
            }
            state = self
                .not_empty
                .wait(state)
                .unwrap_or_else(|e| e.into_inner());
        }
    }

    pub fn close(&self) {
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        state.closed = true;
        self.not_empty.notify_all();
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.state
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .items
            .len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn preserves_fifo_order() {
        let queue = BoundedQueue::new(3);
        queue.try_push(1).unwrap();
        queue.try_push(2).unwrap();
        assert_eq!(queue.pop(), Some(1));
        assert_eq!(queue.pop(), Some(2));
    }

    #[test]
    fn reports_full_without_blocking() {
        let queue = BoundedQueue::new(1);
        queue.try_push(1).unwrap();
        assert_eq!(queue.try_push(2), Err((PushError::Full, 2)));
    }

    #[test]
    fn reports_closed_and_preserves_value() {
        let queue = BoundedQueue::new(1);
        queue.close();
        assert_eq!(queue.try_push(9), Err((PushError::Closed, 9)));
    }

    #[test]
    fn close_unblocks_waiting_consumer() {
        let queue = Arc::new(BoundedQueue::<u64>::new(1));
        let worker_queue = Arc::clone(&queue);
        let handle = thread::spawn(move || worker_queue.pop());
        thread::sleep(Duration::from_millis(10));
        queue.close();
        assert_eq!(handle.join().unwrap(), None);
    }
}
