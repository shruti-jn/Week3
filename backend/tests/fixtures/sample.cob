      *> ─────────────────────────────────────────────────────────────────
      *> LegacyLens — Sample COBOL File for Testing
      *>
      *> This is a minimal but realistic COBOL program that tests can use
      *> to verify that the chunker, parser, and embedder work correctly.
      *>
      *> It contains all four standard COBOL DIVISIONS:
      *> 1. IDENTIFICATION: who wrote this program and when
      *> 2. ENVIRONMENT: what hardware/files this runs on
      *> 3. DATA: what variables/data structures exist
      *> 4. PROCEDURE: the actual business logic (what the program does)
      *>
      *> The PROCEDURE DIVISION has two PARAGRAPHS:
      *> - CALCULATE-INTEREST: computes loan interest
      *> - DISPLAY-RESULT: shows the output to the user
      *>
      *> These paragraphs are what our chunker should detect and split on.
      *> ─────────────────────────────────────────────────────────────────

       IDENTIFICATION DIVISION.
       PROGRAM-ID. SAMPLE-LOAN-CALC.
       AUTHOR. LEGACYLENS.
       DATE-WRITTEN. 2026-03-02.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-370.
       OBJECT-COMPUTER. IBM-370.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
      *> These are the variables used in our calculations
       01 PRINCIPAL       PIC 9(9)V99  VALUE 0.
       01 ANNUAL-RATE     PIC 9(3)V99  VALUE 0.
       01 MONTHLY-RATE    PIC 9(3)V9999 VALUE 0.
       01 NUM-PAYMENTS    PIC 9(3)     VALUE 0.
       01 MONTHLY-PMT     PIC 9(9)V99  VALUE 0.
       01 TOTAL-INTEREST  PIC 9(9)V99  VALUE 0.
       01 WS-RESULT-MSG   PIC X(80)    VALUE SPACES.

       PROCEDURE DIVISION.

      *> ────────────────────────────────────────────────────────────────
      *> CALCULATE-INTEREST
      *>
      *> Computes the monthly payment and total interest for a loan.
      *> Uses the standard amortization formula.
      *>
      *> Formula: M = P * (r(1+r)^n) / ((1+r)^n - 1)
      *> Where:
      *>   P = principal (loan amount)
      *>   r = monthly interest rate (annual rate / 12 / 100)
      *>   n = number of monthly payments
      *>   M = monthly payment amount
      *> ────────────────────────────────────────────────────────────────
       CALCULATE-INTEREST.
           MOVE 100000.00  TO PRINCIPAL
           MOVE 5.25       TO ANNUAL-RATE
           MOVE 360        TO NUM-PAYMENTS

           DIVIDE 1200 INTO ANNUAL-RATE GIVING MONTHLY-RATE

           COMPUTE MONTHLY-PMT =
               PRINCIPAL * (MONTHLY-RATE *
               (1 + MONTHLY-RATE) ** NUM-PAYMENTS) /
               ((1 + MONTHLY-RATE) ** NUM-PAYMENTS - 1)

           COMPUTE TOTAL-INTEREST =
               (MONTHLY-PMT * NUM-PAYMENTS) - PRINCIPAL

           PERFORM DISPLAY-RESULT.

      *> ────────────────────────────────────────────────────────────────
      *> DISPLAY-RESULT
      *>
      *> Shows the calculated loan payment and interest to the user.
      *> Called by CALCULATE-INTEREST after the computation is done.
      *>
      *> COBOL uses DISPLAY to print to the screen (like Python's print).
      *> STRING concatenates multiple values into one output line.
      *> ────────────────────────────────────────────────────────────────
       DISPLAY-RESULT.
           STRING "Monthly Payment: $"
                  MONTHLY-PMT
                  " | Total Interest: $"
                  TOTAL-INTEREST
               DELIMITED SIZE INTO WS-RESULT-MSG

           DISPLAY WS-RESULT-MSG
           STOP RUN.
