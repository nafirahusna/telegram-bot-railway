class SpreadsheetConfig:
    def __init__(self):
        self.table_start_row = 3
        self.table_start_col = "A"
        self.table_end_col = "U"

        self.headers = [
            "Report Type",
            "ID Ticket",
            "Time",
            "Reported",
            "Month",
            "Segmen",
            "Category",
            "Customer Name",
            "Service No",
            "Segment",
            "Teknisi 1",
            "Teknisi 2",
            "STO",
            "Valins ID",
            "Service Type",
            "Status",
            "Resolve",
            "Solution",
            "Job-ID",
            "Team",
            "Foto Eviden",
        ]
        
        self.report_type_options = {
            'non_b2b': 'Non B2B',
            'bges': 'BGES', 
            'squad': 'Squad'
        }
    
    def get_range(self, row_offset=0):
        start_row = self.table_start_row + row_offset
        return f'Sheet1!{self.table_start_col}{start_row}:{self.table_end_col}{start_row}'
    
    def get_column_range(self):
        return f'Sheet1!{self.table_start_col}:{self.table_end_col}'
    
    def get_append_range(self):
        return f'Sheet1!{self.table_start_col}:{self.table_end_col}'
    
    def prepare_row_data(self, laporan_data, row_number):
        from datetime import datetime
        
        reported_time = laporan_data.get('reported', '')
        time_part = reported_time.split(' ')[1] if ' ' in reported_time else datetime.now().strftime("%H:%M")
        current_month = datetime.now().strftime("%B")
        
        row_data = [
            laporan_data.get('report_type', ''),
            laporan_data.get('id_ticket', ''),
            time_part,
            laporan_data.get('reported', ''),
            current_month,
            '',
            '',
            laporan_data.get('customer_name', ''),
            laporan_data.get('service_no', ''),
            laporan_data.get('segment', ''),
            laporan_data.get('teknisi_1', ''),
            laporan_data.get('teknisi_2', ''),
            laporan_data.get('sto', ''),
            laporan_data.get('valins_id', ''),
            '',
            '',
            '',
            '',
            '',
            '',
            laporan_data.get('folder_link', ''),
        ]
        
        return row_data
