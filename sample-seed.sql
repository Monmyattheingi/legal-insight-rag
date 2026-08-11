-- Replace with a verified direct PDF URL.
INSERT INTO ingestion_queue(source_url,law_name,law_number,language,category,legal_status)
VALUES('https://REPLACE/child-rights-law.pdf',
'ကလေးသူငယ် အခွင့်အရေးများဆိုင်ရာဥပဒေ','22/2019','my','child-law','active')
ON CONFLICT(source_url) DO NOTHING;
