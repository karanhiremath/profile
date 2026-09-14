use aos_data::manifest::{builtin_personal, builtin_work, Manifest, SCHEMA};
use aos_data::vault::{Argv0, Vault};
use aos_data::{daily, inbox, search};
use chrono::NaiveDate;
use std::fs;
use std::path::PathBuf;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("aos-data-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn write_manifest(root: &std::path::Path, class: &str) {
    let body = if class == "personal" {
        format!(
            "schema = \"{SCHEMA}\"\nlane = \"ao0\"\nclass = \"personal\"\nname = \"notes\"\n\n[paths]\ndaily = \"02_personal/daily\"\ndaily_name = \"{{date}} {{weekday}}.md\"\ninbox = \"01_in\"\nsearch_roots = [\"01_in\", \"02_personal\"]\n"
        )
    } else {
        format!(
            "schema = \"{SCHEMA}\"\nlane = \"ao0\"\nclass = \"work\"\nname = \"kh\"\n\n[paths]\ndaily = \"daily\"\ndaily_name = \"{{date}}.md\"\ninbox = \"scratch\"\nsearch_roots = [\"daily\", \"scratch\"]\n"
        )
    };
    fs::write(root.join("aos-data.toml"), body).unwrap();
}

#[test]
fn builtins_are_ao0() {
    assert_eq!(builtin_personal().lane, "ao0");
    assert_eq!(builtin_work().class.as_str(), "work");
}

#[test]
fn personal_daily_name_includes_weekday() {
    let dir = scratch("personal");
    write_manifest(&dir, "personal");
    let v = Vault::resolve(Argv0::Notes, Some(&dir)).unwrap();
    let d = NaiveDate::from_ymd_opt(2026, 9, 13).unwrap();
    assert_eq!(v.daily_rel(d), "2026-09-13 Sun.md");
    let path = daily::ensure(&v, d).unwrap();
    assert!(path.ends_with("02_personal/daily/2026-09-13 Sun.md"));
    assert!(path.exists());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn work_daily_name_is_iso() {
    let dir = scratch("work");
    write_manifest(&dir, "work");
    let v = Vault::resolve(Argv0::Kh, Some(&dir)).unwrap();
    let d = NaiveDate::from_ymd_opt(2026, 9, 13).unwrap();
    assert_eq!(v.daily_rel(d), "2026-09-13.md");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn argv0_notes_rejects_work_manifest() {
    let dir = scratch("mismatch");
    write_manifest(&dir, "work");
    let err = Vault::resolve(Argv0::Notes, Some(&dir)).unwrap_err();
    assert!(err.to_string().contains("class mismatch"));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn capture_inbox_and_search() {
    let dir = scratch("cap");
    write_manifest(&dir, "personal");
    let v = Vault::resolve(Argv0::Notes, Some(&dir)).unwrap();
    let path = inbox::add(&v, "unique-aos-data-token").unwrap();
    assert!(path.starts_with(&v.root));
    let hits = search::search(&v, "unique-aos-data-token", 10).unwrap();
    assert_eq!(hits.len(), 1);
    daily::append(&v, NaiveDate::from_ymd_opt(2026, 9, 13).unwrap(), "shipped slice").unwrap();
    let items = inbox::list(&v).unwrap();
    assert_eq!(items.len(), 1);
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn confine_blocks_escape() {
    let dir = scratch("esc");
    write_manifest(&dir, "personal");
    let v = Vault::resolve(Argv0::Notes, Some(&dir)).unwrap();
    let err = v.join("../outside.md").unwrap_err();
    assert!(err.to_string().contains("outside vault") || err.to_string().contains("Escape") || err.to_string().contains("refusing"));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn manifest_rejects_bad_schema() {
    let dir = scratch("schema");
    fs::write(dir.join("aos-data.toml"), "schema = \"nope\"\nlane = \"ao0\"\nclass = \"personal\"\nname = \"notes\"\n").unwrap();
    let err = Manifest::load(&dir.join("aos-data.toml")).unwrap_err();
    assert!(err.to_string().contains("unsupported schema"));
    let _ = fs::remove_dir_all(&dir);
}
