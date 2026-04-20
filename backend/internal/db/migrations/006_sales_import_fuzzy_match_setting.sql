INSERT INTO app_settings (key, value_numeric)
VALUES ('sales_import_fuzzy_match_percent', 85)
ON CONFLICT (key) DO NOTHING;
