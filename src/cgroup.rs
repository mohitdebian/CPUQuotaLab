use crate::Result;
use crate::clock::monotonic_ns;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuotaLevel {
    pub path: PathBuf,
    pub quota_usec: Option<u64>,
    pub period_usec: u64,
    pub capacity_cpus: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CgroupInfo {
    pub mount_point: PathBuf,
    pub relative_path: PathBuf,
    pub absolute_path: PathBuf,
    pub quota_levels: Vec<QuotaLevel>,
    pub effective_quota_cpus: Option<f64>,
    pub affinity_cpus: Vec<u32>,
    pub inherited_cpuset_effective: Option<String>,
    pub host_online_cpus: Option<String>,
    pub rust_available_parallelism: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CgroupSnapshot {
    pub timestamp_ns: u64,
    pub path: PathBuf,
    pub cpu_max: Option<String>,
    pub cpu_max_burst: Option<String>,
    pub cpu_stat: BTreeMap<String, u64>,
    pub cpu_stat_local: BTreeMap<String, u64>,
    pub cpu_pressure: Option<String>,
}

pub fn discover() -> Result<CgroupInfo> {
    let mount_point = find_cgroup2_mount(&fs::read_to_string("/proc/self/mountinfo")?)?;
    let relative_path = find_unified_path(&fs::read_to_string("/proc/self/cgroup")?)?;
    let relative_without_root = relative_path.strip_prefix("/").unwrap_or(&relative_path);
    let absolute_path = mount_point.join(relative_without_root);
    if !absolute_path.exists() {
        return Err(format!(
            "resolved cgroup path does not exist: {}",
            absolute_path.display()
        )
        .into());
    }
    let quota_levels = quota_levels(&absolute_path, &mount_point)?;
    let effective_quota_cpus = quota_levels
        .iter()
        .filter_map(|level| level.capacity_cpus)
        .min_by(f64::total_cmp);
    Ok(CgroupInfo {
        mount_point: mount_point.clone(),
        relative_path,
        absolute_path: absolute_path.clone(),
        quota_levels,
        effective_quota_cpus,
        affinity_cpus: current_affinity_from_status(&fs::read_to_string("/proc/self/status")?)?,
        inherited_cpuset_effective: find_in_ancestors(
            &absolute_path,
            &mount_point,
            "cpuset.cpus.effective",
        )?,
        host_online_cpus: read_trimmed(Path::new("/sys/devices/system/cpu/online"))?,
        rust_available_parallelism: std::thread::available_parallelism()
            .ok()
            .map(std::num::NonZero::get),
    })
}

pub fn snapshot(path: &Path) -> Result<CgroupSnapshot> {
    Ok(CgroupSnapshot {
        timestamp_ns: monotonic_ns()?,
        path: path.to_owned(),
        cpu_max: read_trimmed(&path.join("cpu.max"))?,
        cpu_max_burst: read_trimmed(&path.join("cpu.max.burst"))?,
        cpu_stat: read_flat_u64(&path.join("cpu.stat"))?,
        cpu_stat_local: read_flat_u64(&path.join("cpu.stat.local"))?,
        cpu_pressure: read_trimmed(&path.join("cpu.pressure"))?,
    })
}

pub fn process_cgroup_path(pid: u32) -> Result<PathBuf> {
    find_unified_path(&fs::read_to_string(format!("/proc/{pid}/cgroup"))?)
}

pub fn thread_cgroup_paths(pid: u32) -> Result<BTreeMap<u32, PathBuf>> {
    let mut result = BTreeMap::new();
    for entry in fs::read_dir(format!("/proc/{pid}/task"))? {
        let entry = entry?;
        let tid: u32 = entry.file_name().to_string_lossy().parse()?;
        result.insert(tid, process_cgroup_path(tid)?);
    }
    Ok(result)
}

fn quota_levels(start: &Path, mount: &Path) -> Result<Vec<QuotaLevel>> {
    let mut levels = Vec::new();
    let mut current = Some(start.to_owned());
    while let Some(path) = current {
        if let Some(text) = read_trimmed(&path.join("cpu.max"))? {
            let (quota, period) = parse_cpu_max(&text)?;
            levels.push(QuotaLevel {
                path: path.clone(),
                quota_usec: quota,
                period_usec: period,
                capacity_cpus: quota.map(|q| q as f64 / period as f64),
            });
        }
        if path == mount {
            break;
        }
        current = path.parent().map(Path::to_owned);
    }
    Ok(levels)
}

fn find_in_ancestors(start: &Path, mount: &Path, file: &str) -> Result<Option<String>> {
    let mut current = Some(start.to_owned());
    while let Some(path) = current {
        if let Some(value) = read_trimmed(&path.join(file))?
            && !value.is_empty()
        {
            return Ok(Some(value));
        }
        if path == mount {
            break;
        }
        current = path.parent().map(Path::to_owned);
    }
    Ok(None)
}

fn parse_cpu_max(text: &str) -> Result<(Option<u64>, u64)> {
    let mut fields = text.split_whitespace();
    let max = fields.next().ok_or("cpu.max missing MAX")?;
    let period: u64 = fields.next().ok_or("cpu.max missing PERIOD")?.parse()?;
    if fields.next().is_some() || period == 0 {
        return Err(format!("invalid cpu.max: {text}").into());
    }
    let quota = if max == "max" {
        None
    } else {
        Some(max.parse()?)
    };
    Ok((quota, period))
}

fn find_unified_path(cgroup_text: &str) -> Result<PathBuf> {
    cgroup_text
        .lines()
        .find_map(|line| line.strip_prefix("0::"))
        .map(PathBuf::from)
        .ok_or_else(|| "unified cgroup v2 membership not found".into())
}

fn find_cgroup2_mount(mountinfo: &str) -> Result<PathBuf> {
    for line in mountinfo.lines() {
        let Some((before, after)) = line.split_once(" - ") else {
            continue;
        };
        if !after.starts_with("cgroup2 ") {
            continue;
        }
        let fields: Vec<_> = before.split_whitespace().collect();
        if fields.len() >= 5 {
            return Ok(PathBuf::from(unescape_mount_field(fields[4])));
        }
    }
    Err("cgroup2 mount not found".into())
}

fn unescape_mount_field(value: &str) -> String {
    value
        .replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
}

fn current_affinity_from_status(status: &str) -> Result<Vec<u32>> {
    let list = status
        .lines()
        .find_map(|line| line.strip_prefix("Cpus_allowed_list:\t"))
        .ok_or("Cpus_allowed_list missing from /proc/self/status")?;
    parse_cpu_list(list)
}

fn parse_cpu_list(text: &str) -> Result<Vec<u32>> {
    let mut result = Vec::new();
    for part in text.trim().split(',').filter(|part| !part.is_empty()) {
        if let Some((start, end)) = part.split_once('-') {
            let start: u32 = start.parse()?;
            let end: u32 = end.parse()?;
            if start > end {
                return Err(format!("invalid CPU range: {part}").into());
            }
            result.extend(start..=end);
        } else {
            result.push(part.parse()?);
        }
    }
    if result.is_empty() {
        return Err("empty CPU list".into());
    }
    Ok(result)
}

fn read_trimmed(path: &Path) -> Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(text) => Ok(Some(text.trim().to_owned())),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn read_flat_u64(path: &Path) -> Result<BTreeMap<String, u64>> {
    let Some(text) = read_trimmed(path)? else {
        return Ok(BTreeMap::new());
    };
    let mut values = BTreeMap::new();
    for line in text.lines() {
        let mut fields = line.split_whitespace();
        let Some(key) = fields.next() else { continue };
        let Some(value) = fields.next() else { continue };
        if let Ok(value) = value.parse() {
            values.insert(key.to_owned(), value);
        }
    }
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_finite_and_unlimited_cpu_max() {
        assert_eq!(parse_cpu_max("15000 10000").unwrap(), (Some(15000), 10000));
        assert_eq!(parse_cpu_max("max 100000").unwrap(), (None, 100000));
    }

    #[test]
    fn rejects_invalid_cpu_max() {
        assert!(parse_cpu_max("1 0").is_err());
        assert!(parse_cpu_max("1").is_err());
        assert!(parse_cpu_max("1 2 3").is_err());
    }

    #[test]
    fn parses_cpu_ranges() {
        assert_eq!(
            parse_cpu_list("0-3,8,10-11").unwrap(),
            vec![0, 1, 2, 3, 8, 10, 11]
        );
    }

    #[test]
    fn finds_cgroup_membership() {
        assert_eq!(
            find_unified_path("0::/user.slice/test.scope\n").unwrap(),
            PathBuf::from("/user.slice/test.scope")
        );
    }

    #[test]
    fn finds_mount_with_escaped_space() {
        let line = "29 23 0:26 / /sys/fs/cgroup\\040test rw - cgroup2 cgroup rw";
        assert_eq!(
            find_cgroup2_mount(line).unwrap(),
            PathBuf::from("/sys/fs/cgroup test")
        );
    }
}
