"""Tests for account statement extractor."""

from unittest.mock import MagicMock, patch

import pytest

from app.account_extractor import AccountExtractor


def _make_page(text: str) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    return page


def _mock_pdf(pages_text: list[str]):
    mock_pdf = MagicMock()
    mock_pdf.pages = [_make_page(t) for t in pages_text]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


MARCH_STATEMENT_PAGE_1 = """\
                                                                                    
               CAISSE DESJARDINS                                                    
                                                               Pour la période      
               DU SUD-OUEST DE MONTREAL                                             
               C.D.S. GRIFFINTOWN                                                   
                                                            du 1er mars au 31 mars 2019
               1218, NOTRE-DAME OUEST                                               
               MONTREAL, QC                           Folio 100100     Page 1 de 2  
               H3C 1K5 (514) 380-8000                                               
                                    RELEVÉ DE COMPTE                                
                           SJ 815-30001-4                                           
         JEAN TREMBLAY                                                              
         4000 RUE TEST UNITE 12                                                     
         MONTREAL QC H1A 1A1                                                        
                                                                                    
                                                                                    
                                                                                    
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 MAR VMW Dépôt - Virement Interac                        150.00    150.00  
        1 MAR VMW Retrait - Virement Interac à: / Alex Martin /Remboursement 80.00 70.00
        1 MAR VAP Virement-remboursement / à MC 3        45.50               24.50- 
        1 MAR DCV Dépôt provenant de marge de crédit               24.50     0.00   
        4 MAR VMW Retrait - Virement Interac à: / Sophie Roy /Cadeau 120.00 120.00-
        4 MAR DCV Dépôt provenant de marge de crédit              120.00     0.00   
        7 MAR DI Paie / ACME CORP CANADA ULC                     2 100.75  2 100.75 
        7 MAR VAP Virement-remboursement / à MC 3      2 100.75              0.00   
       11 MAR ACH Achat / MAGASIN DÉPOT                   22.40               22.40- 
       11 MAR DCV Dépôt provenant de marge de crédit               22.40     0.00   
       18 MAR RA Paiement / MC DESJARDINS 03/19        1 340.50            1 340.50-
       18 MAR DCV Dépôt provenant de marge de crédit             1 340.50    0.00   
       20 MAR VMW Retrait - Virement Interac à: / Marc Dupont /Divers 55.00 55.00-
       20 MAR VMW Retrait - Virement Interac à: / Club Sport /Abonnement 180.00 235.00-
       20 MAR VMW Retrait - Virement Interac à: / Locataire A /Meuble 95.00 330.00-
       20 MAR VMW Retrait - Virement Interac à: / Julie Blanc /Repas 210.00 540.00-
       20 MAR DCV Dépôt provenant de marge de crédit              540.00     0.00   
       21 MAR DI Paie / ACME CORP CANADA ULC                     2 250.80  2 250.80 
       21 MAR DI Paie / ACME CORP CANADA ULC                     3 489.70  5 740.50 
       21 MAR XWW Remboursement prêt -AccèsD Internet  5 740.50              0.00   
       22 MAR DI Dépôt direct / ASSURANCE VIE INC                  85.50     85.50  
       22 MAR VAP Virement-remboursement / à MC 3        85.50               0.00   
       28 MAR VMW Virement envoyé à / Loyer 4000 /Loyer 980.00              980.00- 
       28 MAR DCV Dépôt provenant de marge de crédit              980.00     0.00   
                                COMPTE D'EPARGNE ET DE PLACEMENT                    
        Date Code          Description         Frais Retrait    Dépôt     Solde     
      CS   PART DE QUALIFICATION (B)                                                
               Solde reporté                                                 8.25   
                          COMPTE D'EPARGNE ET DE PLACEMENT - REGIME ENREGISTRE      
                                                                                    
        Date Code          Description               Retrait    Dépôt     Solde     
      ES 1 EPARGNE STABLE - REGIME ENREGISTRE D'EPARGNE RETRAITE (REER)             
               Solde reporté                                                 0.00   
      ET 1 Compte d'épargne - CELI (No de contrat : C00000000002)                   
               Solde reporté                                                 1.25   
"""

MARCH_STATEMENT_PAGE_2 = """\
                                                                                    
               CAISSE DESJARDINS                                                    
                                                               Pour la période      
               DU SUD-OUEST DE MONTREAL                                             
               C.D.S. GRIFFINTOWN                                                   
                                                            du 1er mars au 31 mars 2019
               1218, NOTRE-DAME OUEST                                               
               MONTREAL, QC                           Folio 100100     Page 2 de 2  
               H3C 1K5 (514) 380-8000                                               
                                    RELEVÉ DE COMPTE                                
                           SJ 815-30001-4                                           
         JEAN TREMBLAY                                                              
         4000 RUE TEST UNITE 12                                                     
         MONTREAL QC H1A 1A1                                                        
                                                                                    
                                                                                    
                                                                                    
                                      MARGE DE CREDIT                               
        Date Code        Description          Intérêt Avance Remboursement Solde    
      MC 3 MARGE DE CREDIT - REMBOURSEMENT DE CAPITAL                               
               Solde reporté                                              12 500.00 
        1 MAR CT Remboursement automatique / de EOP: 45.50 $ 45.50        12 500.00 
        1 MAR DT Avance au compte EOP                    24.50            12 524.50 
        4 MAR DT Avance au compte EOP                   120.00            12 644.50 
        7 MAR CT Remboursement automatique / de EOP: 2 100.75 $ 0.00 2 100.75 10 543.75
       11 MAR DT Avance au compte EOP                    22.40            10 566.15 
       18 MAR DT Avance au compte EOP                  1 340.50           11 906.65 
       20 MAR DT Avance au compte EOP                   540.00            12 446.65 
       21 MAR REC Remb. en capital - Internet: 5 740.50 $ 0.00   5 740.50  6 706.15 
       22 MAR CT Remboursement automatique / de EOP: 85.50 $ 0.00  85.50   6 620.65 
       28 MAR DT Avance au compte EOP                   980.00            7 600.65 
        Intérêts à jour (non exigibles): 38.75 $ Intérêts en retard (exigibles): 0.00 $
        Taux d'intérêt en vigueur: 3.950 % l'an                                     
        Montant autorisé:  25 000.00 $                                              
        Montant disponible: 17 399.35 $                                             
                                         MESSAGE                                    
                                                                                    
             AVISER VOTRE CAISSE DE TOUT CHANGEMENT D'ADRESSE.                       
                              Aviser votre caisse de tout changement d'adresse.     
                        Veuillez vérifier ce relevé et informer la caisse de toute erreur ou omission.
"""

APRIL_STATEMENT = """\
                                                                                    
               CAISSE DESJARDINS                                                    
                                                               Pour la période      
               DU SUD-OUEST DE MONTREAL                                             
               C.D.S. GRIFFINTOWN                                                   
                                                            du 1er avril au 30 avril 2019
               1218, NOTRE-DAME OUEST                                               
               MONTREAL, QC                           Folio 100100     Page 1 de 1  
               H3C 1K5 (514) 380-8000                                               
                                    RELEVÉ DE COMPTE                                
                           SJ 815-30001-4                                           
         JEAN TREMBLAY                                                              
         4000 RUE TEST UNITE 12                                                     
         MONTREAL QC H1A 1A1                                                        
                                                                                    
                                                                                    
                                                                                    
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        5 AVR IAGA Retrait - GAB Desjardins                                400.00  400.00-
       10 AVR IAGA Retrait - GAB Desjardins                                250.00  650.00-
       15 AVR DI Dépôt direct / ACME CORP CANADA ULC              2 800.00 2 150.00
       20 AVR RA Paiement / MC DESJARDINS 04/19        1 100.00            1 050.00
                                                                                    
                                      MARGE DE CREDIT                               
        Date Code        Description          Intérêt Avance Remboursement Solde    
      MC 3 MARGE DE CREDIT - REMBOURSEMENT DE CAPITAL                               
               Solde reporté                                               7 600.65 
        1 AVR CT Remboursement automatique / de EOP: 2 800.00 $ 32.50  48.75  7 584.40
        Intérêts à jour (non exigibles): 32.50 $ Intérêts en retard (exigibles): 0.00 $
        Taux d'intérêt en vigueur: 3.950 % l'an                                     
        Montant autorisé:  25 000.00 $                                              
        Montant disponible: 17 415.60 $                                             
"""


class TestTransactionCounts:
    def test_march_eop_count(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert len(r.eop_transactions) == 24

    def test_march_loc_count(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert len(r.loc_transactions) == 10

    def test_april_eop_count(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([APRIL_STATEMENT])):
            e = AccountExtractor("test.pdf", "2019-04-01", "2019-04-30")
            r = e.extract()
            assert len(r.eop_transactions) == 4

    def test_april_loc_count(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([APRIL_STATEMENT])):
            e = AccountExtractor("test.pdf", "2019-04-01", "2019-04-30")
            r = e.extract()
            assert len(r.loc_transactions) == 1


class TestLocSummary:
    def test_march_loc_summary(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert r.loc_summary is not None
            assert r.loc_summary.authorized_amount == 25000.00
            assert r.loc_summary.available_amount == pytest.approx(17399.35, abs=0.01)
            assert r.loc_summary.current_balance == pytest.approx(7600.65, abs=0.01)
            assert r.loc_summary.opening_balance == 12500.00

    def test_april_loc_summary(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([APRIL_STATEMENT])):
            e = AccountExtractor("test.pdf", "2019-04-01", "2019-04-30")
            r = e.extract()
            assert r.loc_summary is not None
            assert r.loc_summary.authorized_amount == 25000.00


class TestEopTransactionParsing:
    def test_deposit_vmw(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[0]
            assert tx.code == "VMW"
            assert "Dépôt" in tx.description
            assert tx.depot == pytest.approx(150.00, abs=0.01)
            assert tx.retrait == 0.00
            assert tx.solde == pytest.approx(150.00, abs=0.01)

    def test_withdrawal_vmw(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[1]
            assert tx.code == "VMW"
            assert "Retrait" in tx.description
            assert tx.retrait == pytest.approx(80.00, abs=0.01)
            assert tx.depot == 0.00

    def test_vap_transfer_out(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[2]
            assert tx.code == "VAP"
            assert tx.retrait == pytest.approx(45.50, abs=0.01)
            assert tx.depot == 0.00
            assert "MC 3" in tx.description

    def test_dcv_deposit_from_loc(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[3]
            assert tx.code == "DCV"
            assert tx.depot == pytest.approx(24.50, abs=0.01)
            assert tx.retrait == 0.00

    def test_di_payroll_deposit(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[6]
            assert tx.code == "DI"
            assert "ACME CORP" in tx.description
            assert tx.depot == pytest.approx(2100.75, abs=0.01)

    def test_ach_purchase(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            tx = r.eop_transactions[8]
            assert tx.code == "ACH"
            assert tx.retrait == pytest.approx(22.40, abs=0.01)

    def test_ra_cc_payment(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            ra_txs = [t for t in r.eop_transactions if t.code == "RA"]
            assert len(ra_txs) > 0
            assert "MC DESJARDINS" in ra_txs[0].description
            assert ra_txs[0].retrait == pytest.approx(1340.50, abs=0.01)

    def test_xww_loan_repayment(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            xww_txs = [t for t in r.eop_transactions if t.code == "XWW"]
            assert len(xww_txs) > 0
            assert xww_txs[0].retrait == pytest.approx(5740.50, abs=0.01)

    def test_negative_solde_detected(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            negative_solds = [tx for tx in r.eop_transactions if tx.solde < 0]
            assert len(negative_solds) > 0

    def test_thousands_separator_amount(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            large_depots = [t for t in r.eop_transactions if t.depot >= 1000]
            assert len(large_depots) > 0

    def test_april_iaga_atm_withdrawal(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([APRIL_STATEMENT])):
            e = AccountExtractor("test.pdf", "2019-04-01", "2019-04-30")
            r = e.extract()
            iaga_txs = [t for t in r.eop_transactions if t.code == "IAGA"]
            assert len(iaga_txs) == 2
            assert iaga_txs[0].retrait == pytest.approx(400.00, abs=0.01)
            assert iaga_txs[1].retrait == pytest.approx(250.00, abs=0.01)


class TestLocTransactionParsing:
    def test_ct_remboursement(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            ct_txs = [t for t in r.loc_transactions if t.code == "CT"]
            assert len(ct_txs) > 0
            assert ct_txs[0].remboursement > 0
            assert ct_txs[0].avance == 0.00

    def test_dt_avance(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            dt_txs = [t for t in r.loc_transactions if t.code == "DT"]
            assert len(dt_txs) > 0
            assert dt_txs[0].avance > 0
            assert dt_txs[0].remboursement == 0.00

    def test_rec_capital_repayment(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            rec_txs = [t for t in r.loc_transactions if t.code == "REC"]
            assert len(rec_txs) > 0
            assert rec_txs[0].remboursement > 0
            assert rec_txs[0].avance == 0.00

    def test_april_interest_amount(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([APRIL_STATEMENT])):
            e = AccountExtractor("test.pdf", "2019-04-01", "2019-04-30")
            r = e.extract()
            ct_txs = [t for t in r.loc_transactions if t.code == "CT"]
            assert len(ct_txs) > 0
            assert ct_txs[0].interet > 0

    def test_loc_description_preserves_dollar_amount(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            ct_txs = [t for t in r.loc_transactions if t.code == "CT"]
            for tx in ct_txs:
                assert "EOP:" in tx.description
                assert "$" in tx.description


class TestMetadata:
    def test_metadata_year(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert r.metadata["year"] == 2019

    def test_metadata_dates(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert r.metadata["start_date"] == "2019-03-01"
            assert r.metadata["end_date"] == "2019-03-31"

    def test_metadata_counts(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert r.metadata["eop_count"] == 24
            assert r.metadata["loc_count"] == 10


class TestSectionSkipping:
    def test_no_savings_transactions(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            for tx in r.eop_transactions:
                assert tx.account_type == "eop"
            for tx in r.loc_transactions:
                assert tx.account_type == "loc"

    def test_no_reer_or_celi_transactions(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            total = len(r.eop_transactions) + len(r.loc_transactions) if (r := e.extract()) else 0
            assert total == 34

    def test_solde_reporte_skipped(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            for tx in r.eop_transactions + r.loc_transactions:
                assert "Solde reporté" not in tx.description


class TestToJSON:
    def test_to_json_structure(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            data = e.to_json(r)
            assert "metadata" in data
            assert "eop_transactions" in data
            assert "loc_transactions" in data
            assert "loc_summary" in data
            assert len(data["eop_transactions"]) == 24
            assert len(data["loc_transactions"]) == 10
            assert data["loc_summary"]["current_balance"] == pytest.approx(7600.65, abs=0.01)


class TestEopHeaders:
    def test_compte_offre_exclusive(self):
        with patch("pdfplumber.open", return_value=_mock_pdf([MARCH_STATEMENT_PAGE_1, MARCH_STATEMENT_PAGE_2])):
            e = AccountExtractor("test.pdf", "2019-03-01", "2019-03-31")
            r = e.extract()
            assert len(r.eop_transactions) > 0

    def test_compte_a_haut_rendement(self):
        text = """\
      EOP                     COMPTE A HAUT RENDEMENT DESJARDINS                       
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 SEP DI Dépôt direct / TEST EMPLOYER INC                          550.00    550.00  
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2020-09-01", "2020-09-30")
            r = e.extract()
            assert len(r.eop_transactions) > 0

    def test_compte_a_la_carte(self):
        text = """\
      EOP                                COMPTE À LA CARTE                             
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 DEC DI Dépôt direct / TEST EMPLOYER INC                          875.00    875.00  
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2022-12-01", "2022-12-31")
            r = e.extract()
            assert len(r.eop_transactions) > 0


class TestContinuationLines:
    def test_continuation_line_merged(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 JUN XWW Virement -                                                             
Disnat 65TEST5                                                                            4 500.00 4 500.00
        2 JUN XWW Virement -                                                             
Disnat 65TEST5                                                                            2 180.50 6 680.50
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2020-06-01", "2020-06-30")
            r = e.extract()
            disnat_txs = [t for t in r.eop_transactions if "Disnat" in t.description]
            assert len(disnat_txs) == 2
            assert any(t.retrait == pytest.approx(4500.0, abs=0.01) for t in disnat_txs)
            assert any(t.retrait == pytest.approx(2180.50, abs=0.01) for t in disnat_txs)

    def test_vmw_continuation_merged(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
       10 OCT VMW Retrait - Virement Interac à: / Marché                                         0.00
Autour du monde                                                                          60.00 60.00-
       10 OCT VMW Retrait - Virement Interac à: / Marché                                         0.00
Autour du monde                                                                          60.00 120.00-
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2021-10-01", "2021-10-31")
            r = e.extract()
            marketplace_txs = [t for t in r.eop_transactions if "Marché" in t.description]
            assert len(marketplace_txs) == 2


class TestNewCodes:
    def test_irga_withdrawal(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 DEC IRGA Retrait - GAB Desjardins                                220.00  220.00-
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2021-12-01", "2021-12-31")
            r = e.extract()
            irga_txs = [t for t in r.eop_transactions if t.code == "IRGA"]
            assert len(irga_txs) > 0
            assert all(t.retrait > 0 for t in irga_txs)

    def test_ddi_deposit(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 DEC DDI Dépôt direct - Virement Internet                         375.50 375.50
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2021-12-01", "2021-12-31")
            r = e.extract()
            ddi_txs = [t for t in r.eop_transactions if t.code == "DDI"]
            assert len(ddi_txs) > 0
            assert all(t.depot > 0 for t in ddi_txs)

    def test_dmd_deposit(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 JUL DMD Dépôt mobile                                              125.00 125.00
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2021-07-01", "2021-07-31")
            r = e.extract()
            dmd_txs = [t for t in r.eop_transactions if t.code == "DMD"]
            assert len(dmd_txs) > 0
            assert all(t.depot > 0 for t in dmd_txs)

    def test_apa_withdrawal(self):
        text = """\
      EOP                           COMPTE OFFRE EXCLUSIVE                          
        Date Code          Description         Frais Retrait    Dépôt     Solde     
               Solde reporté                                                 0.00   
        1 JUL APA Paiement automatique - Facture                              55.00 55.00-
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2022-07-01", "2022-07-31")
            r = e.extract()
            apa_txs = [t for t in r.eop_transactions if t.code == "APA"]
            assert len(apa_txs) > 0
            assert all(t.retrait > 0 for t in apa_txs)

    def test_ric_loc_repayment(self):
        text = """\
                                      MARGE DE CREDIT                               
        Date Code        Description          Intérêt Avance Remboursement Solde    
      MC 3 MARGE DE CREDIT - REMBOURSEMENT DE CAPITAL                               
               Solde reporté                                               5 200.00 
        1 DEC RIC Remb. en capital - Internet: 2 800.00 $ 0.00   2 800.00  2 400.00 
        Montant autorisé:  10 000.00 $                                              
        Montant disponible: 7 600.00 $                                              
"""
        with patch("pdfplumber.open", return_value=_mock_pdf([text])):
            e = AccountExtractor("test.pdf", "2022-12-01", "2022-12-31")
            r = e.extract()
            ric_txs = [t for t in r.loc_transactions if t.code == "RIC"]
            assert len(ric_txs) > 0
            assert all(t.remboursement > 0 for t in ric_txs)
