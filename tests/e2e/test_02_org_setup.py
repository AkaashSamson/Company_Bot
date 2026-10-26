import pytest
from playwright.sync_api import expect


def test_act2_sarah_org_setup_and_lead_onboarding(ui):
    """Act 2: Delegated Admin Sarah Chen logs in, provisions Engineering and HR
    departments, verifies duplicate department prevention, and onboards Roy and Marcus.
    """
    print("\n" + "=" * 60, flush=True)
    print("[ACT 2] Sarah Chen Organization Setup & Lead Onboarding", flush=True)
    print("=" * 60, flush=True)

    # 1. POS-ORG-01: Sarah Chen First Login
    print("-> [Act 2.1] Sarah Chen logging in with newly provisioned credentials...", flush=True)
    ui.login("sarah.admin", "Password123!")
    sidebar = ui.page.locator('[data-testid="stSidebar"]')
    expect(sidebar.get_by_text("Sarah Chen", exact=False)).to_be_visible()
    print("   [OK] Sarah Chen logged in successfully with Admin role!", flush=True)

    # 2. POS-ORG-02: Create Engineering & HR Departments
    print("-> [Act 2.2] Navigating to Departments to set up corporate structure...", flush=True)
    ui.navigate_to("Departments")
    expect(ui.page.get_by_role("heading", name="Departments", exact=True)).to_be_visible()

    # Create Engineering
    print("   - Creating Engineering department...", flush=True)
    ui.open_expander("Create Department")
    ui.fill_input("Department name *", "Engineering")
    ui.select_dropdown("Default billable policy", "billable")
    ui.page.get_by_role("button", name="Create department").click()
    expect(ui.page.get_by_text("Department created successfully", exact=False)).to_be_visible()

    # Create Human Resources
    print("   - Creating Human Resources department...", flush=True)
    ui.open_expander("Create Department")
    ui.fill_input("Department name *", "Human Resources")
    ui.select_dropdown("Default billable policy", "non-billable")
    ui.page.get_by_role("button", name="Create department").click()
    expect(ui.page.get_by_text("Department created successfully", exact=False)).to_be_visible()
    print("   [OK] Engineering & Human Resources departments created!", flush=True)

    # 3. NEG-ORG-01: Duplicate Department Name Rejection
    print("-> [Act 2.3] Testing negative validation: duplicate department rejection...", flush=True)
    ui.open_expander("Create Department")
    ui.fill_input("Department name *", "Engineering")
    ui.page.get_by_role("button", name="Create department").click()
    expect(ui.page.get_by_text("already exists", exact=False)).to_be_visible()
    print("   [OK] Duplicate department 'Engineering' correctly rejected with conflict error!", flush=True)

    # 4. POS-ORG-03: Onboard Department Leads (Roy & Marcus)
    print("-> [Act 2.4] Navigating to Users to onboard department leads...", flush=True)
    ui.navigate_to("Users")
    expect(ui.page.get_by_role("heading", name="Users", exact=True)).to_be_visible()

    # Onboard Roy Miller (HR Manager)
    print("   - Onboarding Roy Miller (HR Manager)...", flush=True)
    ui.open_expander("Add User")
    ui.fill_input("Username", "roy.hr")
    ui.fill_input("Name *", "Roy Miller")
    ui.fill_input("Email *", "roy@nexora.com")
    ui.select_dropdown("Role", "Manager")
    ui.select_dropdown("Department", "Human Resources")
    ui.fill_input("Initial password", "Password123!")
    ui.page.get_by_role("button", name="Create user").click()
    expect(ui.page.get_by_text("User Roy Miller created successfully", exact=False)).to_be_visible()

    # Onboard Marcus Vance (Engineering Manager)
    print("   - Onboarding Marcus Vance (Engineering Manager)...", flush=True)
    ui.open_expander("Add User")
    ui.fill_input("Username", "marcus.eng")
    ui.fill_input("Name *", "Marcus Vance")
    ui.fill_input("Email *", "marcus@nexora.com")
    ui.select_dropdown("Role", "Manager")
    ui.select_dropdown("Department", "Engineering")
    ui.fill_input("Initial password", "Password123!")
    ui.page.get_by_role("button", name="Create user").click()
    expect(ui.page.get_by_text("User Marcus Vance created successfully", exact=False)).to_be_visible()
    print("   [OK] Roy Miller & Marcus Vance onboarded as Managers!", flush=True)

    # 5. POS-ORG-04: Sarah Logout
    print("-> [Act 2.5] Sarah Chen logging out...", flush=True)
    ui.logout()
    print("[ACT 2 COMPLETE] Organization hierarchy and leads established!\n", flush=True)
