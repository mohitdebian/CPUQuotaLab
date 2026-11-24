//! Linux thread-affinity helpers used to isolate generator roles.

use std::io;

/// Pins the calling operating-system thread to one logical CPU.
#[allow(unsafe_code)]
pub fn pin_current_thread(cpu: usize) -> io::Result<()> {
    if cpu >= libc::CPU_SETSIZE as usize {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "CPU index exceeds CPU_SETSIZE",
        ));
    }
    // SAFETY: `cpu_set_t` is plain data; zero initialization is the required
    // starting representation for CPU_ZERO. CPU index bounds are checked.
    let mut set: libc::cpu_set_t = unsafe { std::mem::zeroed() };
    // SAFETY: `set` is valid and writable and `cpu` is in range.
    unsafe {
        libc::CPU_ZERO(&mut set);
        libc::CPU_SET(cpu, &mut set);
    }
    // PID 0 means the calling thread on Linux.
    // SAFETY: the pointer and size describe the live `cpu_set_t` above.
    let result = unsafe {
        libc::sched_setaffinity(
            0,
            std::mem::size_of::<libc::cpu_set_t>(),
            std::ptr::from_ref(&set),
        )
    };
    if result == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
