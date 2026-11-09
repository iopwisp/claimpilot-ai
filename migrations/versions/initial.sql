CREATE TABLE users (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);
CREATE TABLE audit_logs (
	id VARCHAR NOT NULL, 
	claim_id VARCHAR, 
	user_id VARCHAR, 
	action VARCHAR NOT NULL, 
	entity_id VARCHAR, 
	details JSON, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE claims (
	id VARCHAR NOT NULL, 
	claim_number VARCHAR, 
	created_by VARCHAR NOT NULL, 
	reviewer_id VARCHAR, 
	claimant_name VARCHAR NOT NULL, 
	policy_number VARCHAR NOT NULL, 
	incident_date DATE NOT NULL, 
	incident_description TEXT NOT NULL, 
	claim_amount NUMERIC(16, 2) NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR NOT NULL, 
	job_id VARCHAR, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (claim_number), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
);
CREATE TABLE sessions (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE analyses (
	id VARCHAR NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	result JSON, 
	model VARCHAR NOT NULL, 
	prompt_version VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (id) ON DELETE CASCADE
);
CREATE TABLE documents (
	id VARCHAR NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	filename VARCHAR NOT NULL, 
	mime VARCHAR NOT NULL, 
	digest VARCHAR NOT NULL, 
	kind VARCHAR, 
	status VARCHAR, 
	pages JSON, 
	metadata_json JSON, 
	uploaded_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (id) ON DELETE CASCADE
);
CREATE TABLE extracted_fields (
	id VARCHAR NOT NULL, 
	document_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	value VARCHAR NOT NULL, 
	page INTEGER NOT NULL, 
	quote TEXT NOT NULL, 
	review VARCHAR, 
	corrected VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);
CREATE TABLE policy_chunks (
	id VARCHAR NOT NULL, 
	document_id VARCHAR NOT NULL, 
	page INTEGER NOT NULL, 
	text TEXT NOT NULL, 
	embedding VECTOR(256) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);
CREATE INDEX ix_audit_logs_claim_id ON audit_logs (claim_id);
CREATE INDEX ix_claims_created_by ON claims (created_by);
CREATE INDEX ix_analyses_claim_id ON analyses (claim_id);
CREATE INDEX ix_documents_claim_id ON documents (claim_id);
CREATE INDEX ix_extracted_fields_document_id ON extracted_fields (document_id);
CREATE INDEX ix_policy_chunks_document_id ON policy_chunks (document_id);
