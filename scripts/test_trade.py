#!/usr/bin/env python3
"""End-to-end integration and failure-mode test suite for AXK Capstone.

Validates the complete 5-stage physical and financial custody lifecycle:
1. Cooperative: lot registration and provenance commitment
2. Inspector: physical grading, moisture test, pass/reject attestation
3. Buyer: escrow funding and lock
4. Logistics: carrier assignment, vehicle plate, waybill, tamper-evident container seal
5. Port / Terminal: gate-in, seal tamper verification, customs clearance
6. Settlement: buyer release, member cooperative split, attestation anchor

Tests both happy-path and adversarial failure modes according to ~/.agent-doctrine.md §1.
"""

import json
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://localhost:8000"

def post(endpoint, data):
    url = f"{BASE_URL}/api/method/axk_capstone.trade_api.{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body).get("message", {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body).get("message", {})
        except Exception:
            return e.code, {"error": body}

def get(endpoint, params=None):
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{BASE_URL}/api/method/axk_capstone.trade_api.{endpoint}{query}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body).get("message", {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body).get("message", {})
        except Exception:
            return e.code, {"error": body}

def get_html(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode("utf-8")


class TestAXKEndToEnd(unittest.TestCase):

    def test_01_overview_and_personas(self):
        status, data = get("overview")
        self.assertEqual(status, 200)
        self.assertIn("lots", data)
        self.assertIn("counts", data)
        self.assertIn("Coffee (parchment)", data["commodities"])

        status, personas = get("personas")
        self.assertEqual(status, 200)
        keys = [p["key"] for p in personas]
        self.assertIn("coop", keys)
        self.assertIn("inspector", keys)
        self.assertIn("logistics", keys)
        self.assertIn("port", keys)
        self.assertIn("buyer", keys)

    def test_02_full_custody_lifecycle_happy_path(self):
        # 1. Register lot
        status, lot = post("register_lot", {
            "commodity": "Coffee (parchment)",
            "quantity_kg": 5000.0,
            "declared_grade": "A",
            "origin": "Huye District, Southern Province, Rwanda",
            "variety": "Bourbon Elite",
            "harvest_date": "2026-10-01"
        })
        self.assertEqual(status, 200)
        lot_ref = lot["lot_ref"]
        self.assertEqual(lot["status"], "Registered")
        self.assertIsNotNone(lot["lot_record"])
        self.assertIsNotNone(lot["lot_digest"])

        # 2. Inspect lot (Pass)
        status, lot = post("inspect_lot", {
            "name": lot_ref,
            "passed": 1,
            "grade": "A",
            "quantity_kg": 5000.0,
            "moisture_pct": 11.5,
            "notes": "Premium quality, zero defects"
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "Approved")
        self.assertTrue(lot["passed"])
        self.assertIsNotNone(lot["inspect_tx"])

        # 3. Buyer Escrow Funding
        status, lot = post("fund_lot", {
            "name": lot_ref,
            "amount_rwf": 17000000.0
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "Funded")
        self.assertIsNotNone(lot["fund_tx"])

        # 4. Logistics Dispatch
        seal_no = "RW-SEAL-TEST-9901"
        status, lot = post("dispatch_logistics", {
            "name": lot_ref,
            "carrier_name": "Rwanda Freight Express",
            "driver_name": "David Mugabo",
            "vehicle_plate": "RAD 882X",
            "seal_number": seal_no,
            "destination_port": "Kigali Logistics Platform"
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "In Transit")
        self.assertEqual(lot["seal_number"], seal_no)
        self.assertIsNotNone(lot["waybill_record"])
        self.assertIsNotNone(lot["waybill_digest"])
        self.assertIsNotNone(lot["dispatch_tx"])

        # 5. Port / Terminal Gate-in & Anti-tamper Verification
        status, lot = post("receive_port", {
            "name": lot_ref,
            "port_name": "Kigali Logistics Platform",
            "container_id": "CONT-TEST-4421",
            "customs_ref": "RW-CUST-TEST-0012",
            "seal_number": seal_no
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "At Port")
        self.assertTrue(lot["seal_verified"])
        self.assertIsNotNone(lot["port_receipt_record"])
        self.assertIsNotNone(lot["port_receipt_digest"])
        self.assertIsNotNone(lot["port_tx"])

        # 6. Settle & Attest
        status, lot = post("confirm_delivery", {
            "name": lot_ref
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "Settled")
        self.assertIsNotNone(lot["attest_tx"])
        self.assertIsNotNone(lot["settlement_record"])

        # 7. Cryptographic Chain of Custody Verification
        status, verify = post("verify_lot", {
            "name": lot_ref
        })
        self.assertEqual(status, 200)
        self.assertTrue(verify["lot_record"], "Lot record hash must verify")
        self.assertTrue(verify["settlement_record"], "Settlement hash must verify")
        self.assertTrue(verify["waybill_record"], "Waybill hash must verify")
        self.assertTrue(verify["port_receipt_record"], "Port receipt hash must verify")

    def test_03_failure_mode_inspection_rejection(self):
        # Register lot
        status, lot = post("register_lot", {
            "commodity": "Maize (dry grain)",
            "quantity_kg": 4000.0,
            "declared_grade": "A",
            "origin": "Rwamagana, Eastern Province, Rwanda",
            "variety": "Local Hybrid",
            "harvest_date": "2026-09-30"
        })
        self.assertEqual(status, 200)
        lot_ref = lot["lot_ref"]

        # Reject inspection due to moisture
        status, lot = post("inspect_lot", {
            "name": lot_ref,
            "passed": 0,
            "grade": "C",
            "quantity_kg": 4000.0,
            "moisture_pct": 16.5,
            "notes": "Moisture exceeds 13.5% threshold",
            "reject_reason": "Moisture above tolerance"
        })
        self.assertEqual(status, 200)
        self.assertEqual(lot["status"], "Rejected")
        self.assertFalse(lot["passed"])
        self.assertEqual(lot["reject_reason"], "Moisture above tolerance")

    def test_04_failure_mode_seal_tamper_detection(self):
        # Register -> Inspect -> Fund -> Dispatch with original seal
        status, lot = post("register_lot", {
            "commodity": "Irish Potato",
            "quantity_kg": 6000.0,
            "declared_grade": "A",
            "origin": "Musanze, Rwanda"
        })
        lot_ref = lot["lot_ref"]
        post("inspect_lot", {"name": lot_ref, "passed": 1, "grade": "A", "quantity_kg": 6000.0})
        post("fund_lot", {"name": lot_ref, "amount_rwf": 1800000.0})
        post("dispatch_logistics", {
            "name": lot_ref,
            "carrier_name": "Swift Logistics",
            "seal_number": "RW-SEAL-ORIGINAL-8811"
        })

        # Attempt to receive at port with tampered/broken seal
        status, err = post("receive_port", {
            "name": lot_ref,
            "seal_number": "RW-SEAL-TAMPERED-0000"
        })
        self.assertEqual(status, 400, "Port must reject tampered seal")
        self.assertIn("Tamper Alert", err.get("error", ""))

    def test_05_failure_mode_invalid_state_transitions(self):
        # 1. Cannot fund an uninspected lot
        status, lot = post("register_lot", {
            "commodity": "Beans (dry)",
            "quantity_kg": 2000.0,
            "declared_grade": "B",
            "origin": "Huye, Rwanda"
        })
        lot_ref = lot["lot_ref"]
        status, err = post("fund_lot", {"name": lot_ref, "amount_rwf": 1500000.0})
        self.assertEqual(status, 400, "Cannot fund registered uninspected lot")

        # 2. Cannot settle an un-funded lot
        status, err = post("confirm_delivery", {"name": lot_ref})
        self.assertEqual(status, 400, "Cannot settle un-funded lot")

    def test_06_failure_mode_nonexistent_lot(self):
        status, err = post("dispatch_logistics", {
            "name": "AXK-NONEXISTENT-LOT-9999",
            "carrier_name": "Test Carrier"
        })
        self.assertEqual(status, 404)
        self.assertIn("error", err)

        status, err = post("receive_port", {
            "name": "AXK-NONEXISTENT-LOT-9999"
        })
        self.assertEqual(status, 404)
        self.assertIn("error", err)

    def test_07_web_routes_and_trace_rendering(self):
        routes = [
            "/trade",
            "/trade/coop",
            "/trade/inspect",
            "/trade/logistics",
            "/trade/port",
            "/trade/buy",
            "/trace",
            "/chain",
            "/trace/lot?ref=AXK-KGL-COFFEE-20261001223155",
            "/trace/AXK-KGL-COFFEE-20261001223155"
        ]
        for r in routes:
            status, html = get_html(r)
            self.assertEqual(status, 200, f"Route {r} must return 200")
            self.assertIn("<html", html.lower(), f"Route {r} must render HTML")


if __name__ == "__main__":
    unittest.main(verbosity=2)
