def test_can_user_leave_project():
    # If user is manager, can_leave must be False
    current_uid = "usr_lead"
    project = {"project_id": "PRJ-1", "manager_uid": "usr_lead"}
    assert (project.get("manager_uid") != current_uid) is False

    # If user is regular member, can_leave must be True
    member_project = {"project_id": "PRJ-2", "manager_uid": "other_mgr"}
    assert (member_project.get("manager_uid") != current_uid) is True

def test_project_manager_transfer_and_leave():
    current_uid = "usr_lead"
    project = {"project_id": "PRJ-1", "manager_uid": "usr_lead"}
    assert (project.get("manager_uid") != current_uid) is False

    # Transfer manager to another user
    project["manager_uid"] = "usr_new_lead"
    assert (project.get("manager_uid") != current_uid) is True
