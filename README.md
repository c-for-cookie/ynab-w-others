# ynab-w-others
Tools for automating budgeting, splitting expenses with others

<!-- GETTING STARTED -->
## Getting Started

Here is how you can setup locally.

### Prerequisites

None

### Installation

1. Clone this repo
   ```sh
   git clone https://github.com/c-for-cookie/ynab-w-others.git
   ```
2. [Optional] Setup virtual environment
3. Install required packages
   ```sh
   pip install -r requirements.txt
   ```
4. Make a copy of `change_me_config.yaml` and enter the following:
   - budget_id
   - shared groups
   - account_holders
   - start_date
   - end_date 
   - period
     Note that there are more fields that are required if you are trying to send the email
5. Run the script
   ```sh
   py ynab_calc_code.py
   ```

<!-- USAGE EXAMPLES -->
## Usage

Use this space to show useful examples of how a project can be used. Additional screenshots, code examples and demos work well in this space. You may also link to more resources.
