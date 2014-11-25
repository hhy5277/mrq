import time
import ujson as json
import urllib2
import os
import pytest


def test_current_job_inspect(worker):

    worker.start(flags="--trace_io")

    job_id = worker.send_task(
        "tests.tasks.general.MongoInsert", {"a": 41, "b": 1, "sleep": 3}, block=False)

    time.sleep(1)

    # Test the HTTP admin API
    admin_worker = json.load(urllib2.urlopen("http://localhost:20020"))

    assert admin_worker["status"] == "full"
    assert len(admin_worker["jobs"]) == 1

    # And now the $1M feature: check which function call is currently running!
    assert "sleep(" in "\n".join(admin_worker["jobs"][0]["stack"])
    assert "tests/tasks/general.py" in "\n".join(
        admin_worker["jobs"][0]["stack"])
    # print "STACK", "\n".join(admin_worker["jobs"][0]["stack"])

    assert admin_worker["jobs"][0]["id"] == str(job_id)

    time.sleep(3)

    admin_worker = json.load(urllib2.urlopen("http://localhost:20020"))

    assert admin_worker["status"] == "wait"
    assert len(admin_worker["jobs"]) == 0
    assert admin_worker["done_jobs"] == 1

    assert len(admin_worker["io"]["types"]) > 0

    assert admin_worker["io"]["tasks"][0][0] == "tests.tasks.general.MongoInsert"
    assert admin_worker["io"]["tasks"][0][1] > 0

    assert admin_worker["io"]["total"] > 0


@pytest.mark.parametrize(["p_testtype", "p_testparams", "p_type", "p_data"], [
    ["mongodb-insert", {"a": 41, "b": 1}, "mongodb.insert", {'collection': 'mrq.tests_inserts'}],
    ["mongodb-find", {"a": 41, "b": 1}, "mongodb.find", {'collection': 'mrq.tests_inserts'}],
    ["mongodb-count", {"a": 41, "b": 1}, "mongodb.count", {'collection': 'mrq.tests_inserts'}],
    ["urllib2-get", {'url': 'http://localhost:20020'}, "http.get", {'url': 'http://localhost:20020'}],
    ["redis-llen", {"key": "test:key"}, "redis.llen", {"key": "test:key"}],
    ["redis-lpush", {"key": "test:key"}, "redis.lpush", {"key": "test:key"}],
])
def test_current_job_trace_io(worker, p_testtype, p_testparams, p_type, p_data):

    report_file = "/tmp/mrq_test_worker_report.json"

    if os.path.isfile(report_file):
        os.remove(report_file)

    worker.start(flags="--trace_io --no_mongodb_ensure_indexes --add_network_latency=0.3 --report_interval=0.1 --report_file=%s" % report_file)

    worker.send_task(
        "tests.tasks.io.TestIo",
        {"test": p_testtype, "params": p_testparams},
        block=False
    )

    io = False

    for i in range(0, 200):

        # Get the worker status via the report_file. Because of the network latency we can't use
        # the HTTP admin.
        if os.path.isfile(report_file):
            with open(report_file, "rb") as f:
                try:
                    read = f.read()
                    admin_worker = json.loads(read)
                except:
                    admin_worker = {}
                if len(admin_worker.get("jobs", [])) > 0:
                    io = admin_worker["jobs"][0].get("io")
                    # Don't take MRQ's IOs as regular IO
                    if io and io["type"] == "mongodb" and io["data"]["collection"] in ["mrq.mrq_jobs", "mrq.mrq_logs"]:
                        io = False
                    else:
                        break

        time.sleep(0.05)

    print io
    assert io
    assert io["type"] == p_type
    assert io["data"] == p_data


def test_trace_long_fetch(worker, httpbin):

    worker.start(flags="--trace_io --report_interval=0.1")

    worker.send_task(
        "tests.tasks.io.TestIo",
        {"test": "urllib2-get", "params": {
            "url": "%s/delay/10" % httpbin.url
        }},
        block=False
    )

    time.sleep(5)

    # Test the HTTP admin API
    admin_worker = json.load(urllib2.urlopen("http://localhost:20020"))

    assert admin_worker["jobs"][0]["io"]["type"] == "http.get"

    time.sleep(5)