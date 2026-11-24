//! Monotonic timestamps shared by separate processes.

use std::io;
use std::sync::OnceLock;
use std::time::Instant;

static EPOCH: OnceLock<Instant> = OnceLock::new();

/// Returns nanoseconds from a process-local monotonic epoch.
///
/// This is suitable for local durations only. Cross-process records use the
/// Linux monotonic clock exposed by `/proc/uptime`-compatible `clock_gettime`
/// through the safe standard-library `Instant` implementation indirectly is
/// not serializable, so we use `libc::clock_gettime` in a narrowly allowed
/// module-level lint exception.
#[must_use]
pub fn local_ns() -> u64 {
    let elapsed = EPOCH.get_or_init(Instant::now).elapsed().as_nanos();
    u64::try_from(elapsed).unwrap_or(u64::MAX)
}

/// Returns Linux `CLOCK_MONOTONIC` in nanoseconds.
#[allow(unsafe_code)]
pub fn monotonic_ns() -> io::Result<u64> {
    clock_ns(libc::CLOCK_MONOTONIC)
}

/// Returns CPU time consumed by all threads in the current process.
#[allow(unsafe_code)]
pub fn process_cpu_time_ns() -> io::Result<u64> {
    clock_ns(libc::CLOCK_PROCESS_CPUTIME_ID)
}

/// Returns CPU time consumed by the current operating-system thread.
#[allow(unsafe_code)]
pub fn thread_cpu_time_ns() -> io::Result<u64> {
    clock_ns(libc::CLOCK_THREAD_CPUTIME_ID)
}

#[allow(unsafe_code)]
fn clock_ns(clock_id: libc::clockid_t) -> io::Result<u64> {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: `ts` is a valid, aligned, writable timespec pointer for the
    // duration of the call. The return value is checked before reading it.
    let rc = unsafe { libc::clock_gettime(clock_id, &raw mut ts) };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    let seconds = u64::try_from(ts.tv_sec)
        .map_err(|_| io::Error::other("clock_gettime returned negative seconds"))?;
    let nanos = u64::try_from(ts.tv_nsec)
        .map_err(|_| io::Error::other("clock_gettime returned negative nanoseconds"))?;
    seconds
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(nanos))
        .ok_or_else(|| io::Error::other("monotonic timestamp overflow"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn monotonic_clock_does_not_go_backwards() {
        let mut previous = monotonic_ns().unwrap();
        for _ in 0..10_000 {
            let current = monotonic_ns().unwrap();
            assert!(current >= previous);
            previous = current;
        }
    }

    #[test]
    fn local_clock_does_not_go_backwards() {
        let a = local_ns();
        let b = local_ns();
        assert!(b >= a);
    }

    #[test]
    fn process_cpu_clock_does_not_go_backwards() {
        let first = process_cpu_time_ns().unwrap();
        std::hint::black_box((0..1_000).fold(0_u64, u64::wrapping_add));
        let second = process_cpu_time_ns().unwrap();
        assert!(second >= first);
    }

    #[test]
    fn thread_cpu_clock_does_not_go_backwards() {
        let first = thread_cpu_time_ns().unwrap();
        std::hint::black_box((0..1_000).fold(0_u64, u64::wrapping_add));
        assert!(thread_cpu_time_ns().unwrap() >= first);
    }
}
