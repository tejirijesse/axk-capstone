app_name = "axk_capstone"
app_title = "AXK Capstone"
app_publisher = "Oghenetejiri Jesse"
app_description = "Stellar verification and settlement layer for AXK Network; chain explorer"
app_email = "mr_otj@yahoo.com"
app_license = "mit"
required_apps = ["axk_network"]

after_install = "axk_capstone.setup.ensure_roles"
after_migrate = "axk_capstone.setup.ensure_roles"
