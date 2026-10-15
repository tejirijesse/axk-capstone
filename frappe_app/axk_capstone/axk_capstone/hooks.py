app_name = "axk_capstone"
app_title = "AXK Capstone"
app_publisher = "AXK Capstone contributors"
app_description = "Stellar verification and settlement layer for AXK Network; chain explorer"
app_email = "156300250+tejirijesse@users.noreply.github.com"
app_license = "mit"
# No required apps beyond Frappe. The synthetic five-year history on /chain appears only
# when a site also has the seed DocTypes installed (see docs/history-dataset.md).

after_install = "axk_capstone.setup.ensure_roles"
after_migrate = "axk_capstone.setup.ensure_roles"
