import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from clipper_pipeline import server


class HybridWorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_job_mode = server.JOB_MODE
        self.original_runs_dir = server.RUNS_DIR
        with server.JOBS_LOCK:
            server.JOBS.clear()
        server.JOB_MODE = "hybrid"

    def tearDown(self) -> None:
        server.JOB_MODE = self.original_job_mode
        server.RUNS_DIR = self.original_runs_dir
        with server.JOBS_LOCK:
            server.JOBS.clear()

    def test_hybrid_job_waits_for_worker(self) -> None:
        job = server.create_job("https://www.youtube.com/watch?v=NAWcNSntfHw")

        self.assertEqual(job["status"], "queued")
        queued = server.get_job(job["id"])
        self.assertEqual(queued["steps"][0]["status"], "queued")

        claimed = server.next_worker_job()

        self.assertEqual(claimed["id"], job["id"])
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(server.next_worker_job(), None)

    def test_complete_worker_job_attaches_handoff_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server.RUNS_DIR = Path(directory)
            job = server.create_job("https://www.youtube.com/watch?v=NAWcNSntfHw")
            server.next_worker_job()

            archive = io.BytesIO()
            handoff = {
                "title": "테스트 영상",
                "channel": "테스트 채널",
                "workerId": "unit-test-worker",
                "clips": [{"index": 1, "title": "테스트 클립"}],
                "files": {
                    "input": "input.mp4",
                    "candidates": "candidates.json",
                    "editConfig": "edit-config-web.json",
                    "render": "renders/clip-001-web.mp4",
                },
            }
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("handoff.json", json.dumps(handoff, ensure_ascii=False))
                zip_file.writestr("input.mp4", b"input")
                zip_file.writestr("candidates.json", "{}")
                zip_file.writestr("edit-config-web.json", "{}")
                zip_file.writestr("renders/clip-001-web.mp4", b"render")

            completed = server.complete_worker_job(job["id"], archive.getvalue())

            self.assertEqual(completed["status"], "done")
            self.assertEqual(completed["progress"], 100)
            self.assertEqual(completed["result"]["processedBy"], "unit-test-worker")
            self.assertEqual(completed["result"]["clips"][0]["title"], "테스트 클립")


if __name__ == "__main__":
    unittest.main()
