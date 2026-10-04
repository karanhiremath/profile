use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Child {
    pub id: String,
    pub role: String,
    pub status: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SupervisorSnapshot {
    pub schema: String,
    pub strategy: String,
    pub host_kinds: Vec<String>,
    pub children: Vec<Child>,
    pub note: String,
}

pub fn snapshot(apply_status: &str, chips_status: &str, router_status: &str) -> SupervisorSnapshot {
    SupervisorSnapshot {
        schema: "cos-voice.supervisor.v1".into(),
        strategy: "rest_for_one".into(),
        host_kinds: vec!["mac".into(), "mac-s".into(), "oma-s".into()],
        children: vec![
            Child {
                id: "apply-host".into(),
                role: "wasm-or-native apply binary".into(),
                status: apply_status.into(),
            },
            Child {
                id: "chip-feed".into(),
                role: "atop dump + otel + job-bus".into(),
                status: chips_status.into(),
            },
            Child {
                id: "router".into(),
                role: "dest -> functional effect plan".into(),
                status: router_status.into(),
            },
        ],
        note: "Elixir OTP supervises these; this snapshot is the portable contract".into(),
    }
}
