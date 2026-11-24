use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Warmup,
    Measurement,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskClass {
    Uniform,
    Short,
    Long,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestWire {
    pub request_id: u64,
    pub sequence_index: u64,
    pub phase: Phase,
    pub class: TaskClass,
    pub seed: u64,
    pub intended_arrival_ns: u64,
    pub scheduler_emit_ns: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ControlEvent {
    WarmupStart,
    MeasurementStart,
    MeasurementEnd,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "message_type", rename_all = "snake_case")]
pub enum ClientMessage {
    Request {
        request: RequestWire,
    },
    Control {
        event: ControlEvent,
        generator_timestamp_ns: u64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Completed,
    DroppedQueueFull,
    DroppedQueueClosed,
    Failed,
    Incomplete,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponseWire {
    pub request_id: u64,
    pub outcome: Outcome,
    pub server_receive_ns: u64,
    pub admission_ns: Option<u64>,
    pub execution_start_ns: Option<u64>,
    pub completion_ns: Option<u64>,
    pub execution_cpu_ns: Option<u64>,
    pub worker_id: Option<usize>,
    pub checksum: Option<u64>,
    pub queue_len_at_admission: usize,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SendRecord {
    pub request: RequestWire,
    pub socket_write_start_ns: u64,
    pub socket_write_end_ns: u64,
    pub sender_backlog_at_start: u64,
    pub write_error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawRequestRecord {
    pub request: RequestWire,
    pub socket_write_start_ns: Option<u64>,
    pub socket_write_end_ns: Option<u64>,
    pub sender_backlog_at_start: Option<u64>,
    pub socket_write_error: Option<String>,
    pub response: Option<ResponseWire>,
    pub final_outcome: Outcome,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_round_trip_is_lossless() {
        let request = RequestWire {
            request_id: 7,
            sequence_index: 6,
            phase: Phase::Measurement,
            class: TaskClass::Long,
            seed: 99,
            intended_arrival_ns: 10,
            scheduler_emit_ns: 11,
        };
        let json = serde_json::to_string(&request).unwrap();
        let decoded: RequestWire = serde_json::from_str(&json).unwrap();
        assert_eq!(decoded.request_id, request.request_id);
        assert_eq!(decoded.class, TaskClass::Long);
    }
}
