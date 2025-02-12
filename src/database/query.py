# src/database/query.py
from sqlalchemy import text
from .db_connection import get_db

def get_all_sellers_data():
    with next(get_db()) as db:
        query = text("""
            SELECT `group`, seller, success_fee, indicative_price, gst, pan, address
            FROM sellers
            ORDER BY `group`, seller
        """)
        result = db.execute(query)

        sellers_data = {}
        for row in result:
            group = row[0]
            seller_info = {
                "seller": row[1],
                "success_fee": row[2],
                "indicative_price": row[3],
                "gst": row[4],
                "pan": row[5],
                "address": row[6]
            }

            if group not in sellers_data:
                sellers_data[group] = []
            sellers_data[group].append(seller_info)

        return sellers_data

def get_devices_by_pan(pan):
    """Get distinct device IDs from inventory2 table for a given PAN number"""
    with next(get_db()) as db:
        query = text("""
            SELECT DISTINCT `Device ID`
            FROM inventory2
            WHERE PAN = :pan
            ORDER BY `Device ID`
        """)
        result = db.execute(query, {"pan": pan})
        return [row[0] for row in result]

def get_months_between(from_month, to_month):
    """Get list of months between two months inclusive"""
    months = ["january", "february", "march", "april", "may", "june",
             "july", "august", "september", "october", "november", "december"]
    # Convert input months to lowercase for comparison
    from_month = from_month.lower()
    to_month = to_month.lower()
    start_idx = months.index(from_month)
    end_idx = months.index(to_month)
    return months[start_idx:end_idx + 1]

def get_invoice_data(device_ids, year, period_from, period_to):
    """Get invoice data for selected devices and period"""
    months = get_months_between(period_from, period_to)

    print("device_ids", device_ids)
    print("year", year)
    print("period_from", period_from)
    print("period_to", period_to)
    
    # Generate dynamic SQL for each month's issued sum
    month_sums = []
    month_issue_process = []
    for month in months:
        month_sums.append(f"SUM(CASE WHEN LOWER(Month) = '{month}' THEN Issued ELSE 0 END) AS `{month}Issued`")
        month_issue_process.append(f"MAX(CASE WHEN LOWER(Month) = '{month}' THEN issue_process ELSE NULL END) AS `{month}IssueProcess`")
    month_sums_sql = ", ".join(month_sums)
    month_issue_process_sql = ", ".join(month_issue_process)
    
    # Convert months to tuple for IN clause
    months_tuple = tuple(months)
    
    with next(get_db()) as db:
        query = text(f"""
            SELECT 
                `Device ID`,
                `Project`,
                MIN(`Capacity (MW)`) AS Capacity,
                SUM(Issued) AS TotalIssued,
                {month_sums_sql},
                {month_issue_process_sql}
            FROM inventory2
            WHERE 
                `Device ID` IN :device_ids AND 
                Year = :year AND 
                LOWER(Month) IN :months AND
                Issued > 0 AND
                invoice_status = 'False'
            GROUP BY `Device ID`, `Project`
        """)
        
        # Prepare parameters
        params = {
            "device_ids": tuple(device_ids),
            "year": year,
            "months": months_tuple
        }
            
        result = db.execute(query, params)
        
        # Convert result to list of dictionaries and process partial issues
        columns = result.keys()
        invoice_data = []
        
        for row in result:
            data = dict(zip(columns, row))
            
            # Add is_partial flag for each month
            for month in months:
                issue_process_key = f"{month}IssueProcess"
                if data.get(issue_process_key):
                    try:
                        issue_process = eval(data[issue_process_key])  # Convert JSON string to Python object
                        data[f"{month}IsPartial"] = len(issue_process) > 1 if isinstance(issue_process, list) else False
                    except:
                        data[f"{month}IsPartial"] = False
                else:
                    data[f"{month}IsPartial"] = False
            
            invoice_data.append(data)
            
        return invoice_data

def get_registered_devices(device_ids):
    """Get list of registered device IDs from invoicereg table"""
    with next(get_db()) as db:
        # Convert comma-separated string to list if needed
        if isinstance(device_ids, str):
            device_ids = device_ids.split(',')
            
        query = text("""
            SELECT `Device ID`
            FROM invoicereg
            WHERE `Device ID` IN :device_ids
        """)
        
        result = db.execute(query, {"device_ids": tuple(device_ids)})
        return ','.join(row[0] for row in result)

def insert_invoice_data(invoice_data):
    """Insert invoice data into the invoicedata table"""
    with next(get_db()) as db:
        query = text("""
            INSERT INTO invoicedata (
                invoiceid, groupName, capacity, regNo, regdevice, issued, ISP,
                registrationFee, issuanceFee, USDExchange, EURExchange,
                invoicePeriodFrom, invoicePeriodTo, gross, regFeeINR, issuanceINR,
                netRevenue, successFee, finalRevenue, project, netRate, pan, gst,
                address, date, deviceIds, companyName
            ) VALUES (
                :invoiceid, :groupName, :capacity, :regNo, :regdevice, :issued, :ISP,
                :registrationFee, :issuanceFee, :USDExchange, :EURExchange,
                :invoicePeriodFrom, :invoicePeriodTo, :gross, :regFeeINR, :issuanceINR,
                :netRevenue, :successFee, :finalRevenue, :project, :netRate, :pan, :gst,
                :address, :date, :deviceIds, :companyName
            )
        """)
        
        db.execute(query, invoice_data)
        db.commit()

def register_devices(device_ids):
    """Register devices in the invoicereg table"""
    with next(get_db()) as db:
        # Convert to list if string
        if isinstance(device_ids, str):
            device_ids = device_ids.split(',')
        
        # Insert each device ID
        for device_id in device_ids:
            query = text("""
                INSERT INTO invoicereg (`Device ID`)
                VALUES (:device_id)
                ON DUPLICATE KEY UPDATE `Device ID` = VALUES(`Device ID`)
            """)
            db.execute(query, {"device_id": device_id.strip()})
        
        db.commit()