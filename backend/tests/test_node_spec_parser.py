"""Tests for the host-facts SSH output parser.

Pure-function tests — no DB / SSH required.
"""
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/k8s_monitor_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def _make_payload(*sections: str) -> str:
    return "\n__NODE_SPEC_SPLIT__\n".join(sections)


def test_os_disk_excluded_via_child_partition():
    """OS 디스크는 자식 partition 의 mountpoint='/' 로 식별돼 non_os 집계에서 제외."""
    from app.routers.node_server_specs import _parse_host_fact_stdout

    lsblk = {
        "blockdevices": [
            {
                "name": "sda", "type": "disk", "size": 500_000_000_000,
                "tran": "sata", "rota": "0", "mountpoint": None,
                "children": [
                    {"name": "sda1", "type": "part", "mountpoint": "/boot/efi"},
                    {"name": "sda2", "type": "part", "mountpoint": "/"},
                ],
            },
            {
                "name": "sdb", "type": "disk", "size": 2_000_000_000_000,
                "tran": "sata", "rota": "1", "mountpoint": None,
            },
        ]
    }
    import json
    out = _parse_host_fact_stdout(_make_payload("[]", json.dumps(lsblk), "none", "Dell Inc."))
    assert out["disk_count"] == 1, "non-OS disk count should be 1 (only sdb)"
    assert out["non_os_disk_gb"] > 0
    assert out["disk_total_gb"] >= out["non_os_disk_gb"]
    assert "HDD (sdb)" in (out["disk_type"] or "")
    assert "sda" not in (out["disk_type"] or ""), "OS disk should not appear in disk_type"


def test_ssd_detection_with_bool_rota():
    """lsblk >= 2.37 은 rota 를 boolean true/false 로 반환 — 정상 처리되어야 함."""
    from app.routers.node_server_specs import _parse_host_fact_stdout

    lsblk = {
        "blockdevices": [
            {
                "name": "sda", "type": "disk", "size": 500_000_000_000,
                "tran": "sata", "rota": False, "mountpoint": None,
                "children": [{"name": "sda1", "type": "part", "mountpoint": "/"}],
            },
        ]
    }
    import json
    out = _parse_host_fact_stdout(_make_payload("[]", json.dumps(lsblk), "none", "Dell Inc."))
    assert out["is_ssd"] is True, "boolean rota=False should be recognized as SSD"


def test_ssd_detection_when_hdd_seen_first():
    """HDD 가 먼저 스캔돼도 이후 SSD 가 나타나면 is_ssd 는 True 로 올라가야 함."""
    from app.routers.node_server_specs import _parse_host_fact_stdout

    lsblk = {
        "blockdevices": [
            {"name": "sda", "type": "disk", "size": 1_000_000_000_000,
             "tran": "sata", "rota": True, "mountpoint": None},
            {"name": "sdb", "type": "disk", "size": 500_000_000_000,
             "tran": "sata", "rota": False, "mountpoint": None,
             "children": [{"name": "sdb1", "type": "part", "mountpoint": "/"}]},
        ]
    }
    import json
    out = _parse_host_fact_stdout(_make_payload("[]", json.dumps(lsblk), "none", "Dell Inc."))
    assert out["is_ssd"] is True, "HDD-then-SSD ordering must not stick is_ssd=False"


def test_nvme_detected_as_ssd():
    from app.routers.node_server_specs import _parse_host_fact_stdout
    import json

    lsblk = {
        "blockdevices": [
            {"name": "nvme0n1", "type": "disk", "size": 1_000_000_000_000,
             "tran": "nvme", "rota": False, "mountpoint": None,
             "children": [{"name": "nvme0n1p1", "type": "part", "mountpoint": "/"}]},
            {"name": "nvme1n1", "type": "disk", "size": 2_000_000_000_000,
             "tran": "nvme", "rota": False, "mountpoint": None},
        ]
    }
    out = _parse_host_fact_stdout(_make_payload("[]", json.dumps(lsblk), "none", "Supermicro"))
    assert out["is_ssd"] is True
    assert out["disk_count"] == 1
    assert "NVMe (nvme1n1)" in (out["disk_type"] or "")
    assert out["is_vm"] is False  # Supermicro = baremetal


def test_vm_detected_via_dmi_when_systemd_missing():
    """systemd-detect-virt 가 없어 fallback 으로 'none' 이 나와도 DMI vendor 로 VM 판정."""
    from app.routers.node_server_specs import _parse_host_fact_stdout
    out = _parse_host_fact_stdout(_make_payload("[]", "{}", "none", "QEMU"))
    assert out["is_vm"] is True


def test_vm_detected_via_systemd_when_dmi_missing():
    from app.routers.node_server_specs import _parse_host_fact_stdout
    out = _parse_host_fact_stdout(_make_payload("[]", "{}", "kvm", "unknown"))
    assert out["is_vm"] is True


def test_baremetal_when_both_signals_agree():
    from app.routers.node_server_specs import _parse_host_fact_stdout
    out = _parse_host_fact_stdout(_make_payload("[]", "{}", "none", "Dell Inc."))
    assert out["is_vm"] is False


def test_is_vm_none_when_both_signals_unknown():
    from app.routers.node_server_specs import _parse_host_fact_stdout
    # systemd raw is empty, DMI is "unknown" fallback
    out = _parse_host_fact_stdout(_make_payload("[]", "{}", "", "unknown"))
    assert out["is_vm"] is None


def test_legacy_three_section_payload_still_parses():
    """오래된 backend 가 3-section payload 를 보내도 파서가 죽지 않아야 한다."""
    from app.routers.node_server_specs import _parse_host_fact_stdout
    out = _parse_host_fact_stdout(_make_payload("[]", "{}", "kvm"))
    assert out["is_vm"] is True  # falls back to systemd-detect-virt only
