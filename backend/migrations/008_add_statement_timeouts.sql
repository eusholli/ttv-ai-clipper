-- Set statement timeout to 10 seconds
ALTER DATABASE CURRENT SET statement_timeout = '10s';

-- Set idle transaction timeout to 30 seconds
ALTER DATABASE CURRENT SET idle_in_transaction_session_timeout = '30s';
