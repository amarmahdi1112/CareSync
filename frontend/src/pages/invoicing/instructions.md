Understood. My apologies for the mix-up. "CareSync" is a fantastic name and implies a lot about its purpose.

I have updated the entire project brief to replace "timesavr" with **"CareSync"**. I also refined the language to better align with a care-focused application. The core technical specifications and features remain the same, as they are perfectly suited for this type of app.

Here is the final, updated markdown file for your agent.

---

# Feature Specification: Dynamic Invoicing Module for CareSync

## 1. High-Level Goal

To integrate a comprehensive, flexible, and user-friendly invoicing module into the **CareSync** application. The system must be expertly designed to handle the diverse billing scenarios faced by care providers—from complex subsidy-based daycare invoices to simple hourly rates for specialized services. The end goal is to empower users to create, manage, track, and export professional invoices seamlessly within the CareSync ecosystem.

## 2. Core User Stories (The "Why")

To build a truly useful tool, we must address the specific needs of our users:

*   **As a Daycare Provider (Complex Billing),** I want to create invoices within CareSync that automatically calculate a parent's portion by subtracting a grant/subsidy from a full rate, so I can ensure billing accuracy and reduce administrative overhead.
*   **As a Caregiver or Support Worker (Hourly Billing),** I want to log my hours for different clients and generate an invoice that automatically calculates the total based on my hourly rate, so I can get paid for my services promptly and professionally.
*   **As a Small Care Facility Owner (Product/Service Billing),** I want to add multiple line items for services and supplies, apply taxes if needed, and save common items so I can create recurring invoices quickly.
*   **As any CareSync User,** I want to save my clients' information, track the status of my invoices (Draft, Sent, Paid, Overdue), and view a complete history of all my billing activities, so I can stay organized and manage my finances effectively.

## 3. Key Features Breakdown (The "What")

The invoicing module will be composed of several interconnected features, creating a complete financial workflow within CareSync:

1.  **Invoice Creation & Live Preview:** A dynamic, real-time invoice generator.
2.  **Client Management (Mini-CRM):** A system to save and manage client and family information.
3.  **Service/Product Management:** A catalog for pre-saving frequently used services and fees.
4.  **Dashboard & History:** An overview of all invoices with status tracking and management tools.
5.  **Settings & Customization:** Personalization for branding, taxes, and payment defaults.
6.  **Exporting & Sharing:** Generating professional PDF documents.

---

## 4. Detailed Feature Specifications (The "How")

### 4.1. The Invoice Generator

The core of the module, featuring a **dual-panel live preview** interface for an intuitive creation experience.

*   **Invoice Fields:**
    *   **Provider Info:** Auto-populated from Settings (Logo, Name, Address, etc.).
    *   **Client Info:** A dropdown to select from saved clients, or fields to add a new one on the fly.
    *   **Invoice Number:** Can be manually entered or auto-generated sequentially (e.g., `INV-2025-001`).
    *   **File Number:** An optional field for client-specific identifiers.
    *   **Dates:** `Invoice Date` (defaults to today) and `Due Date`.
*   **Dynamic Line Items:** This is the most critical part for handling different invoice types. When a user adds a line item, they must select a **`Line Item Type`**:
    *   **Type 1: Daycare (Subsidy/Grant)**
        *   Fields: `Child's Name`, `Full Rate`, `Subsidy/Grant Amount`
        *   Calculation: `Full Rate - Subsidy/Grant Amount`
    *   **Type 2: Service (Hourly)**
        *   Fields: `Description`, `Hours`, `Rate per Hour`
        *   Calculation: `Hours * Rate per Hour`
    *   **Type 3: Service (Flat Rate)**
        *   Fields: `Description`, `Amount`
        *   Calculation: `Amount`
    *   **Type 4: Product/Supply**
        *   Fields: `Item Name`, `Quantity`, `Price per Unit`
        *   Calculation: `Quantity * Price per Unit`
*   **Totals Section:**
    *   **Subtotal:** Auto-calculated sum of all line items.
    *   **Discount:** An optional field for a percentage (%) or flat amount ($).
    *   **Tax:** An optional field for a percentage (%). The user can save default tax rates in Settings.
    *   **Grand Total:** The final amount, calculated automatically.
*   **Footer Section:**
    *   `Notes`: For payment instructions, bank details, etc.
    *   `Terms & Conditions`: For payment terms (e.g., "Payment due within 30 days").

### 4.2. Client Management (Mini-CRM)

A dedicated section within CareSync to manage clients.
*   **Fields for each client:** `Client Name` (Parent or Organization), `Email`, `Phone`, `Address`. Can be linked to existing profiles if the app supports it.
*   **Functionality:**
    *   **Add, Edit, and Delete** clients.
    *   When creating an invoice, a searchable dropdown of clients should be available to auto-fill the "Bill To" section.

### 4.3. Service & Product Catalog

A section to pre-save billable items for quick reuse.
*   **Fields for each item:** `Item Name/Title`, `Default Description`, `Default Rate/Price`.
*   **Functionality:**
    *   **Add, Edit, and Delete** items.
    *   When adding a line item to an invoice, the user can select from this catalog to auto-fill the details.

### 4.4. Dashboard & Invoice History

The central hub for invoice management.
*   **Dashboard View:** A quick overview with key stats:
    *   `Total Overdue Amount`
    *   `Total Outstanding Amount (not yet due)`
    *   `Total Paid (last 30 days)`
*   **History Table:** A comprehensive list of all invoices with the following columns:
    *   `Status` (Draft, Sent, Paid, Overdue) - This is a crucial field.
    *   `Invoice #`
    *   `Client Name`
    *   `Date Issued`
    *   `Amount`
*   **Actions for each invoice:**
    *   `View/Download PDF`
    *   `Edit` (only for "Draft" invoices)
    *   `Duplicate` (creates a new draft with the same details)
    *   `Mark as Sent`, `Mark as Paid`, `Mark as Unpaid`
    *   `Delete`

### 4.5. Settings

*   **Provider Profile:** `Your Name/Company Name`, `Address`, `Phone`, `Email`, `Website`.
*   **Branding:** An option to upload a `Company Logo`.
*   **Financials:**
    *   `Default Currency Symbol` (e.g., $, €, £).
    *   `Default Tax Rates` (e.g., GST 5%, PST 7%) that can be easily applied to invoices.
*   **Invoice Customization:**
    *   `Default Notes` and `Default Terms & Conditions`.
    *   Set a custom `Invoice Number Prefix` (e.g., `CS-`).

---

## 5. Data Models (Example Schema)

This defines the structure of the data to be stored within the CareSync system.

```json
// ProviderProfile
{
  "name": "Discoverers' Daycare",
  "address": "10935 113 STREET...",
  "phone": "(587) 523-5886",
  "email": "discoverersdaycare1@gmail.com",
  "logoUrl": "http://path.to/logo.png",
  "defaultTaxRate": 5,
  "currencySymbol": "$"
}

// Client
{
  "id": "client-123",
  "name": "Bisi Abdi Adam",
  "email": "bisi.a@email.com",
  "address": "10603 111 St NW"
}

// Invoice
{
  "id": "inv-001",
  "invoiceNumber": "INV-2025-001",
  "fileNumber": "1727673",
  "clientId": "client-123",
  "issueDate": "2025-06-01",
  "dueDate": "2025-07-01",
  "status": "Sent", // Draft, Sent, Paid, Overdue
  "lineItems": [
    {
      "id": "item-abc",
      "type": "daycare_subsidy",
      "description": "Hire Salah Adam Abdi - June Toddler Care",
      "fullRate": 1087.00,
      "subsidy": 687.00,
      "total": 400.00
    },
    {
      "id": "item-def",
      "type": "service_hourly",
      "description": "Specialized Support",
      "hours": 10,
      "rate": 50.00,
      "total": 500.00
    }
  ],
  "subtotal": 900.00,
  "taxRate": 5,
  "taxAmount": 45.00,
  "total": 945.00,
  "notes": "Payment can be made via e-transfer to caresync.pay@email.com"
}
```

---

## 6. Technical Recommendations (For a React App)

*   **Framework:** React (using Vite for setup).
*   **State Management:** React Context API with `useReducer` or a lightweight global state manager like Zustand.
*   **Routing:** React Router.
*   **Styling:** Tailwind CSS for rapid, consistent UI development.
*   **PDF Generation:** `@react-pdf/renderer` for maximum control over the PDF layout from React components.
*   **Data Persistence (if client-side):** `localStorage` with JSON serialization. For a more robust solution, consider `IndexedDB` for larger datasets.