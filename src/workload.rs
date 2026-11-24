use std::hint::black_box;

/// Deterministic integer work with data dependencies on every iteration.
#[must_use]
pub fn compute(seed: u64, request_id: u64, iterations: u64) -> u64 {
    let mut value = seed ^ request_id.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    for index in 0..iterations {
        value ^= value >> 12;
        value ^= value << 25;
        value ^= value >> 27;
        value = value
            .wrapping_mul(0x2545_F491_4F6C_DD1D)
            .wrapping_add(index);
    }
    black_box(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn work_is_deterministic() {
        assert_eq!(compute(7, 11, 1000), compute(7, 11, 1000));
    }

    #[test]
    fn inputs_change_result() {
        assert_ne!(compute(7, 11, 1000), compute(8, 11, 1000));
        assert_ne!(compute(7, 11, 1000), compute(7, 12, 1000));
    }

    #[test]
    fn iteration_count_changes_result() {
        assert_ne!(compute(7, 11, 999), compute(7, 11, 1000));
    }
}
