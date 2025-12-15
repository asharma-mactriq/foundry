class OTAService:
    def check_for_updates(self):
        return {"status": "no-update"}

    def push_update(self, version):
        print("[OTA] Pushing update:", version)

ota_service = OTAService()
