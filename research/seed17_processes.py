"""Small JSON-line RPC clients; reference and model children have separate heaps."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


class ProcessClient:
    def __init__(self, root, module, args, *, session=False):
        self.root, self.module, self.args, self.use_session = Path(root), module, args, session
        self.process = None
        self.token = secrets.token_hex(32)

    def call(self, message):
        if self.process is None:
            env = os.environ.copy()
            if self.use_session:
                env["SEED17_WORKER_SESSION"] = self.token
            self.process = subprocess.Popen([sys.executable, "-u", "-m", self.module, *map(str, self.args)],
                cwd=self.root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        if self.use_session:
            message = {**message, "session": self.token}
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Child interrupted; preserve journal and resume explicitly")
        result = json.loads(line)
        if result.get("rpc_error"):
            raise RuntimeError("Reference service rejected request")
        return result

    def close(self):
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)


class ModelProcess(ProcessClient):
    def __init__(self, root, run_dir):
        super().__init__(root, "research.seed17_worker", [run_dir], session=True)

    def predict(self, request):
        return self.call(request)


class OracleProcess(ProcessClient):
    def __init__(self, root, bundle):
        super().__init__(root, "research.seed17_oracle_service", [bundle])

    def index(self):
        return self.call({"op": "index"})["index"]

    def answer(self, **query):
        return self.call({"op": "answer", **query})["answer"]
