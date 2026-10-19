-- PharmaCompare database schema
-- Matches the ER diagram in the Phase-2 PPT (slide 9) exactly: 10 tables.
-- Run this once via init_db.py (or paste into MySQL Workbench) to create all tables.

CREATE TABLE IF NOT EXISTS Users (
    user_id     INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    email       VARCHAR(150) NOT NULL UNIQUE,
    phone       VARCHAR(20),
    password    VARCHAR(255) NOT NULL,
    -- Added beyond the original PPT: self-declared drug allergies (JSON array
    -- of strings), used by the allergy check. NULL = never declared.
    allergies   JSON NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Prescriptions (
    prescription_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    image_path       VARCHAR(500) NOT NULL,
    -- Added beyond the original PPT ER diagram: lets the user label a
    -- prescription ("Dr. Sharma visit - Jan 2026") instead of only seeing
    -- a generated filename in their history.
    prescription_name VARCHAR(255),
    -- Added for the symptom-selection + prescription-type feature: purely
    -- user-supplied context, stored as-is, never used to diagnose or
    -- auto-analyze anything at this stage.
    prescription_type VARCHAR(100),
    symptoms         JSON,
    upload_date      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status           VARCHAR(50) NOT NULL DEFAULT 'uploaded',
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS OCR_Results (
    ocr_id          INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    extracted_text  TEXT,
    -- Added beyond the original PPT ER diagram: the same text as
    -- extracted_text, broken into per-line objects with EasyOCR's own
    -- per-line confidence, so uncertain lines can be flagged individually
    -- instead of only having one confidence score for the whole page.
    line_results    JSON,
    confidence_score DECIMAL(5,2),
    processed_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_id) REFERENCES Prescriptions(prescription_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Medicines (
    medicine_id   INT AUTO_INCREMENT PRIMARY KEY,
    medicine_name VARCHAR(255) NOT NULL,
    composition   VARCHAR(300),
    form          VARCHAR(50),
    strength      VARCHAR(50),
    category      VARCHAR(100),
    -- Everything below is added beyond the original PPT ER diagram, to
    -- support importing and matching against a real medicine dataset.
    -- Data currently comes from a COMMUNITY-COMPILED dataset
    -- (github.com/junioralive/Indian-Medicine-Dataset, MIT licensed) -
    -- NOT an official/government-verified source. See database/PROVENANCE.md.
    primary_salt      VARCHAR(150),
    secondary_salt    VARCHAR(150),
    manufacturer      VARCHAR(150),
    pack_size         VARCHAR(100),
    -- Modified-release mechanism (sr, er, cr, pr, dt, odt, chewable, ec, mr, modified);
    -- NULL = conventional release. Derived from pack_size/name by
    -- app/services/release_type.py. Two tablets with the same salt and strength
    -- are only interchangeable when this matches.
    release_type      VARCHAR(12) NULL,
    -- 1 when the name shows 3+ strengths but composition lists <= 2 ingredients
    -- (the source CSV only has two composition columns). See app/services/composition.py.
    composition_incomplete BOOLEAN NOT NULL DEFAULT FALSE,
    price             DECIMAL(10,2),
    is_discontinued   BOOLEAN NOT NULL DEFAULT FALSE,
    source_dataset_id VARCHAR(20),
    data_source       VARCHAR(150) NOT NULL DEFAULT 'community_dataset:indian-medicine-dataset-github',
    imported_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FULLTEXT idx_med_search (medicine_name, composition),
    -- Supports brand-name prefix lookup during Medicine Detection. FULLTEXT
    -- relevance alone buries an exact brand behind thousands of generic
    -- products that share its salt ("Montek LC Tablet" ranked 2801st of 4945
    -- for "Monte*"), so the matcher also looks the written brand up directly.
    INDEX idx_medicine_name (medicine_name),
    INDEX idx_primary_salt (primary_salt),
    INDEX idx_discontinued (is_discontinued)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Added beyond the original PPT ER diagram, for the Clinical Decision
-- Engine: a reference table of known drug-drug interaction pairs.
-- Data source: DDInter 2.0 (Nucleic Acids Research, Oxford Academic,
-- peer-reviewed, free, no registration - https://ddinter2.scbdd.com).
-- See database/PROVENANCE.md. This is NOT a diagnosis system - absence of
-- a row here is never treated as proof of safety (enforced in application
-- code, not just here).
CREATE TABLE IF NOT EXISTS Drug_Interactions (
    interaction_id  INT AUTO_INCREMENT PRIMARY KEY,
    drug_a          VARCHAR(150) NOT NULL,
    drug_b          VARCHAR(150) NOT NULL,
    drug_a_norm     VARCHAR(150) NOT NULL,  -- lowercased, for matching
    drug_b_norm     VARCHAR(150) NOT NULL,
    severity        VARCHAR(30) NOT NULL,   -- DDInter's own scale, kept verbatim: Major/Moderate/Minor/Unknown
    data_source     VARCHAR(150) NOT NULL DEFAULT 'DDInter 2.0 (ddinter2.scbdd.com)',
    imported_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_drug_a_norm (drug_a_norm),
    INDEX idx_drug_b_norm (drug_b_norm)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Prescription_Medicines (
    pm_id           INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    -- Nullable, changed from the original PPT's NOT NULL: an OCR line that
    -- doesn't confidently match any real Medicines row has no valid
    -- medicine_id yet ("Needs Verification" - see match_status below).
    medicine_id     INT NULL,
    dosage          VARCHAR(100),
    frequency       VARCHAR(100),
    duration        VARCHAR(100),
    -- Added beyond the original PPT ER diagram, for Medicine Detection:
    raw_text         VARCHAR(500),
    match_confidence DECIMAL(5,4),
    match_status     VARCHAR(30) NOT NULL DEFAULT 'needs_verification',
    -- Close runners-up when several medicines matched about equally well
    -- (JSON array); NULL when the match was unambiguous.
    match_options    JSON NULL,
    FOREIGN KEY (prescription_id) REFERENCES Prescriptions(prescription_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id) REFERENCES Medicines(medicine_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS AI_Analysis (
    analysis_id     INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    summary         TEXT,
    risk_level      VARCHAR(50),
    analysis_date   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_id) REFERENCES Prescriptions(prescription_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Added beyond the original PPT ER diagram: one row per individual safety
-- finding for a prescription (a prescription can have several), feeding
-- into the single AI_Analysis summary row above. This is the Clinical
-- Decision Engine's structured output - never a diagnosis, always
-- carrying its own confidence, explanation and data source.
CREATE TABLE IF NOT EXISTS Safety_Findings (
    finding_id          INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id     INT NOT NULL,
    issue_type          VARCHAR(30) NOT NULL,   -- interaction | duplicate | dosage_inconsistency | allergy_check
    medicines_involved   JSON,                   -- [{medicine_id, medicine_name}, ...]
    severity            VARCHAR(30) NOT NULL,   -- Major | Moderate | Minor | Unknown | NEEDS_VERIFICATION
    confidence           DECIMAL(5,4),
    explanation          TEXT NOT NULL,
    recommendation        TEXT NOT NULL,
    data_source           VARCHAR(150) NOT NULL,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_id) REFERENCES Prescriptions(prescription_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- pharmacy_name changed from the original PPT's NOT NULL to nullable: we
-- have one imported reference price per product (see PROVENANCE.md), not
-- real per-pharmacy prices, so it stays NULL until a genuine multi-pharmacy
-- price source exists. Everything else below is added beyond the original
-- PPT ER diagram, for the Price Comparison service.
CREATE TABLE IF NOT EXISTS Price_Comparison (
    price_id         INT AUTO_INCREMENT PRIMARY KEY,
    pm_id            INT NOT NULL,
    medicine_id      INT NOT NULL,   -- which product this price row describes
    row_type         VARCHAR(20) NOT NULL,   -- 'prescribed' | 'alternative'
    pharmacy_name    VARCHAR(150),
    price            DECIMAL(10,2) NOT NULL,
    price_per_unit   DECIMAL(10,4),
    pack_size        VARCHAR(100),
    price_difference DECIMAL(10,2),  -- vs the prescribed medicine; NULL on the prescribed row itself
    savings_percent  DECIMAL(6,2),
    is_discontinued  BOOLEAN NOT NULL DEFAULT FALSE,
    data_source      VARCHAR(150) NOT NULL,
    price_date       DATETIME NOT NULL,   -- when this price was captured in OUR source dataset, not "now"
    last_updated     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pm_id) REFERENCES Prescription_Medicines(pm_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id) REFERENCES Medicines(medicine_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Added beyond the original PPT ER diagram: recommended_medicine_id,
-- reason, and data_source. generic_name/price_difference/confidence_score
-- are the PPT's own fields, kept and populated as designed - generic_name
-- holds the recommended alternative's product name. Never generated for
-- a medicine Medicine Detection didn't confirm, and never picks a
-- "winner" - lists up to 3 cheaper, same-composition options with the
-- facts behind each, same as Price Comparison's own honesty rules.
CREATE TABLE IF NOT EXISTS Generic_Recommendations (
    gr_id                    INT AUTO_INCREMENT PRIMARY KEY,
    pm_id                    INT NOT NULL,
    recommended_medicine_id  INT NOT NULL,
    generic_name             VARCHAR(200) NOT NULL,
    price_difference         DECIMAL(10,2),
    confidence_score         DECIMAL(5,2),
    reason                   TEXT NOT NULL,
    data_source              VARCHAR(150) NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pm_id) REFERENCES Prescription_Medicines(pm_id) ON DELETE CASCADE,
    FOREIGN KEY (recommended_medicine_id) REFERENCES Medicines(medicine_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Smart_Health_Report (
    report_id       INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    report_file     VARCHAR(500),
    generated_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prescription_id) REFERENCES Prescriptions(prescription_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS System_Logs (
    log_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id   INT,
    action    VARCHAR(150) NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details   TEXT,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Data_Sources, Pharmacies and Pharmacy_Offers are ADDITIVE and start EMPTY. Empty offers mean no pharmacy has reported anything.
-- Data_Sources: a registry of the data used (kinds: reference_dataset, interaction_dataset, pharmacy_feed, synthetic_demo).
-- license is NULL when it is not recorded. retrieved_at is when we obtained the data, not when it was true.
CREATE TABLE IF NOT EXISTS Data_Sources (
    source_id     INT AUTO_INCREMENT PRIMARY KEY,
    source_key    VARCHAR(80) NOT NULL UNIQUE,
    name          VARCHAR(200) NOT NULL,
    kind          VARCHAR(30) NOT NULL,
    url           VARCHAR(500),
    license       VARCHAR(200),
    record_count  INT,
    retrieved_at  DATETIME,
    notes         TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS Pharmacies (
    pharmacy_id INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    city        VARCHAR(100) NOT NULL DEFAULT '',
    address     VARCHAR(255),
    source_id   INT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_pharmacy (name, city, source_id),
    FOREIGN KEY (source_id) REFERENCES Data_Sources(source_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Partner_Keys: API keys for pharmacy partners who PUSH reports (POST /api/feeds/offers). Only the SHA-256 hash of a key is stored: the key
-- is shown once, when database/manage_partner_keys.py creates it. Starts EMPTY: no partner exists until someone creates one.
CREATE TABLE IF NOT EXISTS Partner_Keys (
    key_id       INT AUTO_INCREMENT PRIMARY KEY,
    source_id    INT NOT NULL,
    label        VARCHAR(100) NOT NULL,
    key_prefix   CHAR(8) NOT NULL,
    key_hash     CHAR(64) NOT NULL UNIQUE,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME NULL,
    revoked_at   DATETIME NULL,
    FOREIGN KEY (source_id) REFERENCES Data_Sources(source_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Pharmacy_Offers: one row per observation a pharmacy reported. price is NULL when only stock was reported.
-- availability is in_stock, limited, out_of_stock or unknown. observed_at is required: a report with no time is not accepted.
CREATE TABLE IF NOT EXISTS Pharmacy_Offers (
    offer_id           INT AUTO_INCREMENT PRIMARY KEY,
    pharmacy_id        INT NOT NULL,
    medicine_id        INT NOT NULL,
    price              DECIMAL(10,2),
    availability       VARCHAR(20) NOT NULL DEFAULT 'unknown',
    quantity_available INT,
    observed_at        DATETIME NOT NULL,
    imported_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_observation (pharmacy_id, medicine_id, observed_at),
    INDEX idx_offer_medicine (medicine_id, observed_at),
    FOREIGN KEY (pharmacy_id) REFERENCES Pharmacies(pharmacy_id) ON DELETE CASCADE,
    FOREIGN KEY (medicine_id) REFERENCES Medicines(medicine_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
