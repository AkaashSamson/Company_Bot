from app.db.sequences import next_sequence, prefix_number


class FakeCounters:
    def __init__(self):
        self.counters = {}

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        name = query["_id"]
        inc = update.get("$inc", {}).get("seq", 0)
        self.counters[name] = self.counters.get(name, 0) + inc
        return {"_id": name, "seq": self.counters[name]}


class FakeDatabase:
    def __init__(self):
        self.counters = FakeCounters()

    def __getitem__(self, name):
        if name == "counters":
            return self.counters
        raise KeyError(name)


def test_prefix_number_pads_to_min_digits():
    assert prefix_number("MSS", 1, 3) == "MSS001"
    assert prefix_number("MSS", 42, 3) == "MSS042"
    assert prefix_number("DOC", 7, 3) == "DOC007"
    assert prefix_number("MSS", 1234, 3) == "MSS1234"


def test_next_sequence_increments():
    db = FakeDatabase()
    assert next_sequence("employee_id", db) == 1
    assert next_sequence("employee_id", db) == 2
    assert next_sequence("employee_id", db) == 3


def test_next_sequence_is_restart_safe_within_run():
    db = FakeDatabase()
    assert next_sequence("employee_id", db) == 1
    assert next_sequence("employee_id", db) == 2
    new_db = FakeDatabase()  # simulates a restart without counter persistence data
    assert next_sequence("employee_id", new_db) == 1


def test_distinct_counters_advance_independently():
    db = FakeDatabase()
    assert next_sequence("employee_id", db) == 1
    assert next_sequence("document_id", db) == 1
    assert next_sequence("employee_id", db) == 2
    assert next_sequence("document_id", db) == 2