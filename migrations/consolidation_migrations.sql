-- HostelFlow Consolidation Database Migrations
-- This script contains all database changes needed for the consolidation

-- =====================================================
-- Phase 1: Create new unified data models
-- =====================================================

-- Party model for unified guest/staff/vendor management
CREATE TABLE IF NOT EXISTS party (
    id SERIAL PRIMARY KEY,
    party_type VARCHAR(50) NOT NULL, -- 'guest', 'staff', 'vendor'
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120),
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for party table
CREATE INDEX IF NOT EXISTS idx_party_type ON party(party_type);
CREATE INDEX IF NOT EXISTS idx_party_email ON party(email);

-- Unified Transaction/Ledger model
CREATE TABLE IF NOT EXISTS transaction (
    id SERIAL PRIMARY KEY,
    party_id INTEGER REFERENCES party(id),
    transaction_type VARCHAR(50) NOT NULL, -- 'payment', 'expense', 'refund', 'salary'
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'MAD',
    description TEXT,
    reference VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES "user"(id)
);

-- Create indexes for transaction table
CREATE INDEX IF NOT EXISTS idx_transaction_party ON transaction(party_id);
CREATE INDEX IF NOT EXISTS idx_transaction_type ON transaction(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transaction_created_at ON transaction(created_at);

-- DomainEvent table for audit and analytics
CREATE TABLE IF NOT EXISTS domain_event (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    user_id INTEGER REFERENCES "user"(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for domain_event table
CREATE INDEX IF NOT EXISTS idx_domain_event_type ON domain_event(event_type);
CREATE INDEX IF NOT EXISTS idx_domain_event_aggregate ON domain_event(aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_domain_event_created_at ON domain_event(created_at);

-- Shared StockItem model for inventory and housekeeping
CREATE TABLE IF NOT EXISTS stock_item (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    unit_of_measurement VARCHAR(20),
    current_stock DECIMAL(10,2) DEFAULT 0,
    reorder_point DECIMAL(10,2) DEFAULT 0,
    cost_per_unit DECIMAL(10,2),
    supplier_id INTEGER REFERENCES party(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for stock_item table
CREATE INDEX IF NOT EXISTS idx_stock_item_category ON stock_item(category);
CREATE INDEX IF NOT EXISTS idx_stock_item_active ON stock_item(is_active);

-- =====================================================
-- Phase 2: Migrate existing data to new models
-- =====================================================

-- Migrate guests to party table
INSERT INTO party (party_type, name, email, phone, created_at, updated_at)
SELECT 
    'guest' as party_type,
    name,
    email,
    phone,
    created_at,
    COALESCE(updated_at, created_at) as updated_at
FROM tenant
WHERE NOT EXISTS (
    SELECT 1 FROM party p 
    WHERE p.party_type = 'guest' 
    AND p.name = tenant.name 
    AND p.email = tenant.email
);

-- Migrate staff to party table
INSERT INTO party (party_type, name, email, phone, created_at, updated_at)
SELECT 
    'staff' as party_type,
    full_name as name,
    email,
    NULL as phone, -- Staff phone not stored in user table
    created_at,
    updated_at
FROM "user"
WHERE is_active = TRUE
AND NOT EXISTS (
    SELECT 1 FROM party p 
    WHERE p.party_type = 'staff' 
    AND p.name = "user".full_name 
    AND p.email = "user".email
);

-- Migrate payments to transaction table
INSERT INTO transaction (party_id, transaction_type, amount, currency, description, reference, created_at, created_by)
SELECT 
    p.id as party_id,
    'payment' as transaction_type,
    amount,
    'MAD' as currency,
    CONCAT('Payment for guest: ', t.name) as description,
    CONCAT('PAY-', payment.id) as reference,
    payment.payment_date as created_at,
    NULL as created_by -- Payment creator not tracked in current model
FROM payment
JOIN tenant t ON payment.tenant_id = t.id
JOIN party p ON p.party_type = 'guest' 
    AND p.name = t.name 
    AND (p.email = t.email OR (p.email IS NULL AND t.email IS NULL))
WHERE NOT EXISTS (
    SELECT 1 FROM transaction tr 
    WHERE tr.reference = CONCAT('PAY-', payment.id)
);

-- Migrate expenses to transaction table
INSERT INTO transaction (party_id, transaction_type, amount, currency, description, reference, created_at, created_by)
SELECT 
    NULL as party_id, -- Expenses don't have associated parties in current model
    'expense' as transaction_type,
    amount,
    'MAD' as currency,
    CONCAT(description, ' - ', category) as description,
    CONCAT('EXP-', expense.id) as reference,
    date as created_at,
    NULL as created_by -- Expense creator not tracked in current model
FROM expense
WHERE NOT EXISTS (
    SELECT 1 FROM transaction tr 
    WHERE tr.reference = CONCAT('EXP-', expense.id)
);

-- Migrate inventory items to stock_item table
INSERT INTO stock_item (name, category, unit_of_measurement, current_stock, reorder_point, cost_per_unit, is_active, created_at, updated_at)
SELECT 
    name,
    category,
    unit_of_measurement,
    current_stock,
    reorder_point,
    cost_per_unit,
    is_active,
    created_at,
    COALESCE(updated_at, created_at) as updated_at
FROM inventory_item
WHERE NOT EXISTS (
    SELECT 1 FROM stock_item si 
    WHERE si.name = inventory_item.name 
    AND si.category = inventory_item.category
);

-- =====================================================
-- Phase 3: Create audit event triggers
-- =====================================================

-- Function to create domain events for audit
CREATE OR REPLACE FUNCTION create_domain_event()
RETURNS TRIGGER AS $$
BEGIN
    -- Determine event type based on operation
    DECLARE
        event_type VARCHAR(100);
        aggregate_id VARCHAR(100);
        aggregate_type VARCHAR(50);
        event_data JSONB;
    BEGIN
        -- Set aggregate info based on table
        IF TG_TABLE_NAME = 'tenant' THEN
            aggregate_type := 'guest';
            aggregate_id := NEW.id::TEXT;
        ELSIF TG_TABLE_NAME = 'payment' THEN
            aggregate_type := 'payment';
            aggregate_id := NEW.id::TEXT;
        ELSIF TG_TABLE_NAME = 'expense' THEN
            aggregate_type := 'expense';
            aggregate_id := NEW.id::TEXT;
        ELSIF TG_TABLE_NAME = 'inventory_item' THEN
            aggregate_type := 'inventory';
            aggregate_id := NEW.id::TEXT;
        ELSE
            aggregate_type := TG_TABLE_NAME;
            aggregate_id := NEW.id::TEXT;
        END IF;
        
        -- Set event type based on operation
        IF TG_OP = 'INSERT' THEN
            event_type := aggregate_type || '_created';
        ELSIF TG_OP = 'UPDATE' THEN
            event_type := aggregate_type || '_updated';
        ELSIF TG_OP = 'DELETE' THEN
            event_type := aggregate_type || '_deleted';
        END IF;
        
        -- Create event data
        event_data := jsonb_build_object(
            'operation', TG_OP,
            'table', TG_TABLE_NAME,
            'old_data', CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE NULL END,
            'new_data', CASE WHEN TG_OP != 'DELETE' THEN to_jsonb(NEW) ELSE NULL END
        );
        
        -- Insert domain event
        INSERT INTO domain_event (event_type, aggregate_id, aggregate_type, event_data, created_at)
        VALUES (event_type, aggregate_id, aggregate_type, event_data, CURRENT_TIMESTAMP);
        
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for audit events
CREATE TRIGGER tenant_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON tenant
    FOR EACH ROW EXECUTE FUNCTION create_domain_event();

CREATE TRIGGER payment_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON payment
    FOR EACH ROW EXECUTE FUNCTION create_domain_event();

CREATE TRIGGER expense_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON expense
    FOR EACH ROW EXECUTE FUNCTION create_domain_event();

CREATE TRIGGER inventory_item_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON inventory_item
    FOR EACH ROW EXECUTE FUNCTION create_domain_event();

-- =====================================================
-- Phase 4: Create views for backward compatibility
-- =====================================================

-- View for guest data with party integration
CREATE OR REPLACE VIEW guest_view AS
SELECT 
    t.id,
    t.name,
    t.email,
    t.phone,
    t.daily_rent,
    t.deposit,
    t.start_date,
    t.end_date,
    t.is_active,
    t.checkout_date,
    t.created_at,
    p.id as party_id
FROM tenant t
LEFT JOIN party p ON p.party_type = 'guest' 
    AND p.name = t.name 
    AND (p.email = t.email OR (p.email IS NULL AND t.email IS NULL));

-- View for payment data with transaction integration
CREATE OR REPLACE VIEW payment_view AS
SELECT 
    p.id,
    p.tenant_id,
    p.amount,
    p.payment_date,
    p.payment_method,
    p.status,
    p.created_at,
    tr.id as transaction_id,
    tr.party_id
FROM payment p
LEFT JOIN transaction tr ON tr.reference = CONCAT('PAY-', p.id);

-- View for expense data with transaction integration
CREATE OR REPLACE VIEW expense_view AS
SELECT 
    e.id,
    e.amount,
    e.description,
    e.category,
    e.date,
    e.created_at,
    tr.id as transaction_id
FROM expense e
LEFT JOIN transaction tr ON tr.reference = CONCAT('EXP-', e.id);

-- =====================================================
-- Phase 5: Create indexes for performance
-- =====================================================

-- Additional indexes for performance
CREATE INDEX IF NOT EXISTS idx_transaction_amount ON transaction(amount);
CREATE INDEX IF NOT EXISTS idx_transaction_created_by ON transaction(created_by);
CREATE INDEX IF NOT EXISTS idx_domain_event_user ON domain_event(user_id);
CREATE INDEX IF NOT EXISTS idx_stock_item_supplier ON stock_item(supplier_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_transaction_party_type ON transaction(party_id, transaction_type);
CREATE INDEX IF NOT EXISTS idx_domain_event_aggregate_created ON domain_event(aggregate_type, aggregate_id, created_at);

-- =====================================================
-- Phase 6: Data integrity checks
-- =====================================================

-- Function to verify data migration integrity
CREATE OR REPLACE FUNCTION verify_migration_integrity()
RETURNS TABLE(
    check_name TEXT,
    expected_count BIGINT,
    actual_count BIGINT,
    status TEXT
) AS $$
BEGIN
    -- Check guest migration
    RETURN QUERY
    SELECT 
        'Guests migrated to party'::TEXT as check_name,
        (SELECT COUNT(*) FROM tenant WHERE is_active = TRUE)::BIGINT as expected_count,
        (SELECT COUNT(*) FROM party WHERE party_type = 'guest')::BIGINT as actual_count,
        CASE 
            WHEN (SELECT COUNT(*) FROM tenant WHERE is_active = TRUE) = 
                 (SELECT COUNT(*) FROM party WHERE party_type = 'guest')
            THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status;
    
    -- Check payment migration
    RETURN QUERY
    SELECT 
        'Payments migrated to transaction'::TEXT as check_name,
        (SELECT COUNT(*) FROM payment)::BIGINT as expected_count,
        (SELECT COUNT(*) FROM transaction WHERE transaction_type = 'payment')::BIGINT as actual_count,
        CASE 
            WHEN (SELECT COUNT(*) FROM payment) = 
                 (SELECT COUNT(*) FROM transaction WHERE transaction_type = 'payment')
            THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status;
    
    -- Check expense migration
    RETURN QUERY
    SELECT 
        'Expenses migrated to transaction'::TEXT as check_name,
        (SELECT COUNT(*) FROM expense)::BIGINT as expected_count,
        (SELECT COUNT(*) FROM transaction WHERE transaction_type = 'expense')::BIGINT as actual_count,
        CASE 
            WHEN (SELECT COUNT(*) FROM expense) = 
                 (SELECT COUNT(*) FROM transaction WHERE transaction_type = 'expense')
            THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status;
    
    -- Check inventory migration
    RETURN QUERY
    SELECT 
        'Inventory items migrated to stock_item'::TEXT as check_name,
        (SELECT COUNT(*) FROM inventory_item)::BIGINT as expected_count,
        (SELECT COUNT(*) FROM stock_item)::BIGINT as actual_count,
        CASE 
            WHEN (SELECT COUNT(*) FROM inventory_item) = 
                 (SELECT COUNT(*) FROM stock_item)
            THEN 'PASS'::TEXT
            ELSE 'FAIL'::TEXT
        END as status;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Phase 7: Cleanup and optimization
-- =====================================================

-- Analyze tables for query optimization
ANALYZE party;
ANALYZE transaction;
ANALYZE domain_event;
ANALYZE stock_item;

-- Update table statistics
UPDATE pg_stat_user_tables 
SET n_tup_ins = 0, n_tup_upd = 0, n_tup_del = 0 
WHERE schemaname = 'public' 
AND relname IN ('party', 'transaction', 'domain_event', 'stock_item');

-- =====================================================
-- Migration completion summary
-- =====================================================

-- Create a migration log entry
INSERT INTO domain_event (event_type, aggregate_id, aggregate_type, event_data, created_at)
VALUES (
    'migration_completed',
    'consolidation_migration',
    'system',
    jsonb_build_object(
        'migration_name', 'consolidation_migrations',
        'version', '1.0',
        'tables_created', 4,
        'triggers_created', 4,
        'views_created', 3,
        'indexes_created', 12,
        'completed_at', CURRENT_TIMESTAMP
    ),
    CURRENT_TIMESTAMP
);

-- Display migration summary
SELECT 
    'Consolidation Migration Completed' as status,
    (SELECT COUNT(*) FROM party) as parties_created,
    (SELECT COUNT(*) FROM transaction) as transactions_created,
    (SELECT COUNT(*) FROM domain_event) as events_created,
    (SELECT COUNT(*) FROM stock_item) as stock_items_created;
