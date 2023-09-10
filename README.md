<!-- NB any links not defined as aboslute will not resolve on PyPI page -->
# beanahead

[![PyPI](https://img.shields.io/pypi/v/beanahead)](https://pypi.org/project/beanahead/) ![Python Support](https://img.shields.io/pypi/pyversions/beanahead) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Beanahead administers future transactions for [beancount][beancount] ledgers.

It let's you:
- Generate regular expected transactions.
- Define ad hoc expected transactions.
- Reconcile expected transactions against imported transactions.

It's useful to:
- Forecast account balances based on expected income and payments.
- Add transactions between updating accounts.

## Installation

`$ pip install beanahead`

The only direct dependencies are `beancount` and `pandas` (pandas could be made optional, see [#1](https://github.com/maread99/beanahead/issues/1)).

> :information_source: The `beancount` requirement is beancount v2. It's intended that `beanahead` will be upgraded to support beancount v3 (currently in development) when v3 is completed and published to PyPI.

## Really briefly, how it works

- Expected transactions are defined on separate ledgers.
- Newly imported entries are reconciled against expected transactions before being included to the main ledger (**beanahead does not need to touch your main ledger**).

## Briefly, how it works
- Regular Expected Transactions (electicity bill, rent, etc) are defined by including a single transaction to a dedicated beancount file, by convention 'rx_def.beancount'.
- The `addrx` command is used to populate a Regular Expected Transactions ledger with transactions. This ledger, by convention 'rx.beancount', is 'included' to your main .beancount ledger.
- ad hoc Expected Transactions are added to the Expected Transactions ledger, by convention 'x.beancount'. This ledger is also 'included' to your main .beancount ledger.
- The `recon` comamnd offers a cli to reconcile newly imported transactions with transactions on the expected transactions ledgers.
  - Newly imported transactions are updated to reflect any missing narration, tags, meta and 'other side' postings defined on the corresponding expected transactions.
  - Reconciled expected transactions are removed from their respective ledgers.

In keeping with the `beancount` spirit, `beanahead` provides all its functionality via a CLI (the underlying functions are available within the codebase should you prefer). There are five commands, all subcommands of `beanahead`.
```
$ beanahead --help
usage: beanahead [-h] [--version] {make,addrx,recon,exp,inject} ...

subcommands:
  {make,addrx,recon,exp,inject}
    make                make a new beanahead file.
    addrx               add Regular Expected Transactions.
    recon               reconcile new transactions.
    exp                 administer expired expected transactions.
    inject              inject new transactions.
```

> :information_source: Wherever this README shows the output from a `--help` option, only an abridged version of the output is shown. Run the command at the command line for the full help, e.g. `beanahead --help`. For subcommands the help includes the documentation of the underlying function.

# Using beanahead

## Index
* [Making beanahead files](#making-beanahead-files)
* [Regular Expected Transactions](#regular-expected-transactions)
  * [Defining regular transactions](#defining-regular-transactions)
    * [freq](#freq)
    * [Postings](#postings)
    * [roll](#roll)
    * [final](#final)
  * [Updating definitions](#updating-definitions)
  * [Adding regular transactions](#adding-regular-transactions)
* [ad hoc transactions](#ad-hoc-transactions)
* [Defining the payee](#defining-the-payee)
* [Reconciling](#reconciling)
  * [Matching](#matching)
  * [Updating](#updating)
* [Injection](#injection)
* [Expired expected transactions](#expired-expected-transactions)
* [Worth remembering](#worth-remembering)
* [Alternative packages](#alternative-packages)
* [beancount recommendations](#beancount-recommendations)
* [Licence](#license)

## Making beanahead files

First off, you'll need to use the `make` command to create a new `.beancount` file or three.

> :information_source: You'll probably want these files to be in the same directory as your exisitng main ledger. The following examples assume you want to create the files in the current working directory. Pass the --dirpath (or -d) option to specify a different directory.

If you want to include Regular Expected Transactions you'll need to create a definitions file and a dedicated ledger....
```
$ beanahead make rx_def -f rx_def
$ beanahead make rx -f rx
```
...and add the following line towards the top of your main ledger.
```
include "rx.beancount"
```
If you want to include ad hoc Expected Transactions you'll need to create a separate dedicated ledger...
```
$ beanahead make x -f x
```
...and add the following line towards the top of your main ledger.
```
include "x.beancount"
```

So, if you want to include both regular and ad hoc expected transactions then you should have created three new `.beancount` files and added two 'include' lines to top of your main ledger.

> :information_source: The -f option provides for defining the filename (`make` will add the `.beancount` extension). If -f is not passed then default names will be used which are as those explicitly passed in the examples.

> :information_source: The quoted file in the 'include' lines should reflect the path to the expected transactions ledger from the directory in which your main ledger is located. The above examples assume that the expected transactions ledgers have the default filenames and are located in the same directory as the main ledger.

The [examples/new_empty_files](./examples/new_empty_files) folder includes a sample of each of the above newly created files.
- [Regular Expected Transaction Definitions file](./examples/new_empty_files/rx_def.beancount)
- [Regular Expected Transactions Ledger](./examples/new_empty_files/rx.beancount)
- [Expected Transactions Ledger](./examples/new_empty_files/x.beancount)

## Regular Expected Transactions

Regular expected transactions are defined on the Regular Expected Transaction _Definitions_ file. The `addrx` command can then be used to populate the Regular Expected Transactions _Ledger_ with transactions generated from these definitions.

### Defining regular transactions

A new regular transaction can be defined at any time by adding a single transaction to the definitions file (the 'initial definition'). The date of this transaction will serve as the anchor off which future transactions are evaluated.

The following initial definition would generate regular transactions on the 5th of every month, with the first generated transaction dated 2022-10-05. 
```beancount
2022-10-05 * "EDISON" "Electricity, monthly fixed tarrif"
  freq: "m"
  Assets:US:BofA:Checking                     -65.00 USD
  Expenses:Home:Electricity
```

Each initial definition must:
- have a **unique [payee](#defining-the-payee)**.
- include the [freq](#freq) meta field to define the transaction frequency.
- include at least two [postings](#postings) of which at least one should be to a balance sheet account ("Assets" or "Liabilities").

Initial definitions can optionally include:
- the [roll](#roll) meta field to define if transactions falling on weekends should roll forwards.
- the [final](#final) meta field to define the last transaction date.
- additional [postings](#postings).
- custom meta fields.
- tags

[rx_defs.beancount][rx_defs_initial] offers an example of a new definitions file before any transactions have been generated. The initial definitions there cover a variety of circumstances, based loosely on selected sampling of beancount's [example.beancount][beancount_example] ledger.

#### freq
The **freq** meta field is used to specify the frequency with which regular transactions should be generated.

A **simple frequency** can be specified as "w", "m" and "y", respectively for weekly, monthly and yearly. The unit can be prefixed with a value to specify a multiple, for example "2w" for fortnightly or "3m" for quarterly.

Alternatively, the frequency can be specified with a **[pandas frequency](https://pandas.pydata.org/docs/user_guide/timeseries.html#offset-aliases)**. For example "BAS-MAR" defines the frequency as the first business day of every March.

#### Postings
Each definition must include a posting to an account which the regular transactions will appear on the statements of. This can be an "Assets" account (for example, for Direct Debits) or a "Liabilities" account (for example, for regular charges to a credit card). If the amount is variable then just stick in an estimate or the amount that you wish to budget for.

At least one posting to an account on the 'other side' must be included (e.g. to an "Expenses" account). Any number of other postings can be included.

When the regular expected transactions are later reconciled with transactions imported from your statements, the `recon` command will update the imported transactions with these 'other-side' postings (see [reconciling](#reconciling)).

> :information_source: If the transaction is balanced with only one 'other-side' posting then you're better off not including an amount for it. (By including an amount, if the imported transaction has a different amount then you'll need to manually amend the posting on the updated imported transaction.)

> :information_source: If the transaction is split between various 'other-side' postings then it will be necessary to define an amount for at least all but one of these. In this case, if the imported transaction value differs from the expected transaction value then you may want to revise the amounts of those postings for which estimates were included.

#### Roll
By default, any generated transaction that would be dated on a weekend will be rolled forward to the following Monday. This behaviour can be overriden by the 'roll' meta field.
```
2022-11-13 * "ETrade Transfer" "Transfering accumulated savings to other account"
  freq: "3m"
  roll: FALSE
  Assets:US:BofA:Checking                       -4000 USD
  Assets:US:ETrade:Cash
```
The above initial definition is dated 2022-11-13, which is a Sunday. By specifying roll as FALSE the first transaction generated will be dated 2022-11-13 regardless that this is a Sunday. Thereafter transactions will be defined on the 13th of each month regardless of whether these dates represent weekdays or weekends.

> :warning: the roll field's value must be in captials and NOT quoted.

> :information_source: initial definitions should always be dated on the 'usual' payment day even if that falls on a weekend. For example...
> ```
> 2022-10-16 * "Verizon" "Telecoms, monthly variable"
> freq: "m"
> Assets:US:BofA:Checking                       -55.00 USD
> Expenses:Home:Phone
>```
> This initial definition is dated 2022-10-16 which is a Sunday. The first generated transaction will be automatcially rolled forward to 2022-10-17. All transactions thereafter will be dated as the 16th of each month whenever the 16th is a weekday or otherwise rolled forward to the following Monday.

#### Final
The 'final' meta field can be used to define a final transaction date. No transactions will be generated that would be dated later than this date (as evaluated prior to any rolling).
```
2022-10-31 * "Chase" "Chase Hire Purchase"
  freq: "BM"
  final: 2022-11-30
  Liabilities:US:Chase:HirePurchase                322.00 USD
  Assets:US:BofA:Checking
```

> :warning: the final field's value should NOT be quoted.

A definition will be automaticaly removed from the definitions file after any final transaction has been generated.

### Updating definitions
The `addrx` command updates the definitions file whenever the ledger is populated with new transactions:
- any definition for which a new transaction was generated will be updated to reflect the transaction that would immediately follow the last transaction that was added to the ledger.
- Defintions are grouped by balance sheet account* and type of account(s) of the 'other side', for example 'Income', 'Expenses' etc. Each group is introduced with a title row. Within each group definitions are sorted by payee. (*The balance sheet account is assumed as the first "Assets" or "Liabilities" account defined in the postings.)

> :information_source: New definitions can be added at any time anywhwere under the line ```;; Enter definitions after this line...``` - they'll find their way to the corresponding section when the file is next updated.

[rx_def_updated.beancount][rx_def_updated] is the updated [rx_def.beancount][rx_defs_initial] file after adding regular transactions to the ledger through to 2022-12-31. :warning: Notice that all comments are lost when a definitions file is updated.

### Adding regular transactions
The `addrx` command is used to populate a Regular Expected Transactions Ledger with transactions evaluated from a definitions file.
```
$ beanahead addrx --help
usage: beanahead addrx [-h] [-e] defs rx-ledger main-ledger

positional arguments:
  defs         path to Regular Expected Transactions Definition file.
  rx-ledger    path to Regular Expected Transactions Ledger file.
  main-ledger  path to main Ledger file.

optional arguments:
  -h, --help   show this help message and exit
  -e , --end   date to which to create new transactions, iso format,e.g. '2020-09-30'. Default 2023-01-11.
```
For example...
```
$ beanahead addrx rx_def rx ledger -e 2022-12-31
```
The above command:
- Gets the definitions from the file `rx_def.beancount` in the current working directory.
- For each definition, generates transactions from the defintion date through to '2022-12-31' (both inclusive).
- Adds transactions to the `rx.beancount` ledger.
- Updates the `rx_def.beancount` file (as [Updating definitions](#updating-definitions)).
- Verifies that the main ledger, `ledger.beancount`, loads without errors. The path to the main ledger is passed as the third positional argument (this ledger should be the main ledger to which the 'insert "rx.beancount"' line was added). `addrx` requires this file only to verify that no errors have arisen as a result of introducing the new transactions to the Regular Expected Transactions Ledger.
  - In the event the main ledger loads with errors then changes made to the definitions file and Regular Expected Transactions Ledger are reverted and advices printed.

If the command is executed as above with the files in the [examples/defs](./examples/defs) folder then the empty rx ledger there will be populated with transactions. The rx ledger would end up as [rx_updated.beancount](./examples/defs/rx_updated.beancount) whilst the definitions file would be updated as [rx_def_updated.beancount][rx_def_updated].

## ad hoc transactions
Creating ad hoc expected transactions is as simple as adding transactions to an Expected Transactions Ledger created via `$ beanahead make x <filename>`. The [x.beancount][x_ledger] file offers an example (again, loosely based on selected sampling of beancount's [example.beancount][beancount_example] ledger).

Jotting down ad hoc transactions is useful to record transaction details 'in the moment' when you have in mind the 'other-side' postings and maybe know the narration or tag that you might forget by the time you next get round to downloading statements and updating your main ledger.

Transactions can be listed on the ledger in any order. Whenever a transaction on the ledger is reconciled with an imported transaction (extracted from a statement) the ledger is rewritten and any remaining transactions are reordered.

> :warning: Any comments will be lost whenever an Expected Transactions Ledger is rewritten.

## Defining the **payee**

The reconciliation of imported transactions with expected transactions ([reconciling](#Reconciling)) can be greatly aided by judiciously naming the expected transactions payee.

Beanahead will treat each 'word' defined in the expected payee as a separate string. An expected payee will match with the payee of any new transaction that includes **any** of those strings. So:
  - Do not include short words that represent common syllables.
    For example, "Top of the World" will match with "The corner shop", "Another Day" and "Super Offers".
  - Use few unambiguous words. For example "Top World". Even just "Top" might be a better choice.

> :information_source: The transaction that ends up on your main ledger will have the payee as defined on the statement, not "Top"!
> :information_source: matches are case-insensitive

## Reconciling 

The `recon` command provides for reconciling imported transactions with expected transactions.

```
$ beanahead recon --help
usage: beanahead recon [-h] [-o OUTPUT] [-k] [-r] new ledgers [ledgers ...]

positional arguments:
  new                   path to new transactions beancount file. Can be
                        absolute or relative to the current working directory.
  ledgers               paths to one or more Regular Expected Transactions
                        Ledgers against which to reconcile incoming
                        transactions.

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        path to which to write updated new entries. Can be
                        absolute or relative to the current working directory.
                        By default will overwrite 'incoming'.
  -k, --keep, --no-remove
                        flag to not remove reconciled transactions from ledgers.
                        (By default reconciled transactions will be removed.)
  -r, --reverse         flag to write updated entries in descending order. By
                        default will be written in ascending order.
```
For example...
```
$ beanahead recon extraction rx x -o injection
```
The above command:
- Gets beancount entries from the file `extraction.beancount` located in the current working directory. This file should contain only new entries as returned by the beancount `extract` command and destined for your beancount ledger.
- Gets the expected transactions from the ledger files `rx.beancount` and `x.beancount`, also located in the current working directory.
- [Matches](#Matching) expected transactions with new transactions.
  - The user is requested to confirm or reject each propsosed match.
  - Where an expected transaction matches more than one new transaction, the user is requested to select which of the new transactions to match (or none).
- [Updates](#Updating) matched new transactions with information gleaned from the corresponding expected transaction.
- Outputs the updated entries. By default overwrites the file passed as the `new` argument (`extraction.beancount` above). Alternatively, a path can be passed to the `--output` option, as in this case where output will be written to `injection.beancount` in the current working directory.
  - Entries are by default sorted in ascending order. Pass the `-r` flag or `--reverse` option to sort in descending order.
- Removes reconciled expected transactions from their respective ledgers. (The `-k` flag can be passed to 'keep' the expected transactions.)

If the command is executed as above with the files in the [examples/recon](./examples/recon) folder and the matches are confirmed then:
- an `injection.beancount` file will be created that looks like [this](./examples/recon/expected_injection.beancount).
- reconciled transactions will be removed from [rx.beancount](./examples/recon/rx.beancount), such that it ends up like [this](./examples/recon/rx_updated.beancount).
- reconciled transactions will be removed from [x.beancount](./examples/recon/x.beancount), such that it ends up like [this](./examples/recon/x_updated.beancount).

### Matching
Beanahead matches expected with imported transactions based on:
- payee (see [Defining the payee](#defining-the-payee))
- similarity in accounts
- closeness of dates
- closeness of amounts

As a bare minimum, matches require that the new and expected transactions:
- are dated within 5 days of each other
- include a posting to the same Asset account
- either have matching payee or the imported transaction amount is no more than 2% different from the expected

If you want a better insight into how matches are evaluated, check out the [reconcile](./src/beanahead/reconcile.py) module to get under-the-bonnet.

### Updating
Beanahead will update the following fields of matched imported transactions to include any values specifed for the corresponding expected transaction. Any existing values on the imported transaction will **not** be overwritten.
- **narration**
- **tags** (excluding #rx_txn and #x_txn)
- **meta** (excluding beanahead meta fields such as 'final', 'roll' etc)
- **postings**
  - postings on the expected transactions will be added to the imported transaction if the imported transaction does not otherwise include a posting to the corresponding account.
  - if the imported and expected transactions include postings to the same account and only the expected transaction defines a number, the imported transaction's posting will be updated to reflect the value as defined on the expected transaction.

## Injection
The output from `recon` can be copied directly into your main ledger. If you're happy to append the full contents 'as is' to the end of your ledger then the `inject` command will do it for you.
```
$ beanahead inject --help
usage: beanahead inject [-h] injection ledger

positional arguments:
  injection   path to beancount file containing the new entries to be
              injected. Can be absolute or relative to the current
              working directory.
  ledger      path to beancount ledger to which new entires are to
              be appended. Can be absolute or relative to the current
              working directory.
```
So...
```
$ beanahead inject injection my_ledger
```
...would append the updated entires in the `injection.beancount` file to the end of the `my_ledger.beancount` file (both files in the current working directory).

## Expired expected transactions
Now that your main ledger has been updated with the new entries it'll be necessary to `bean-check` it to see if all's well. Chances are you'll have to enter some manual postings to balance some transactions.

It's also possible that your balance checks are failing because some expected transactions were included in the new entries although weren't matched (and so now are duplicated), or simply didn't come in (that credit you were waiting for). Beanahead can't chase your debtors but the `exp` command can at least deal with any expired expected transactions.
```
$ beanahead exp --help
usage: beanahead exp [-h] ledgers [ledgers ...]

positional arguments:
  ledgers     paths to one or more Regular Expected Transactions Ledgers
              against which to administer expired transactions.
```
For example:
```
$ beanahead exp rx x
```
The above command:
- Gets the transactions on the expected transactions ledger files 'rx.beancount' and 'x.beancount' (both in the current working directory).
- Offers the user the following options for each transaction that is dated prior to 'today'.
  - Move transaction forwards to 'tomorrow'.
  - Move transaction forwards to a user-defined date.
  - Remove transaction from ledger.
  - Leave transaction as is.
- Rewrites the expected transactions ledgers (if applicable) to reflect the requested changes.

With a bit of luck and perhaps a tweak or two to your ledger, your `bean-check` should now be checking out.

> :information_source: An alternative to using `exp` is to manually redate / remove transactions on the expected transactions ledgers.

## Worth remembering
> :warning: Whenever an expected transactions ledger or the regular expected transaction definition files are updated the entries are resorted and the file is overwritten - anything that is not a directive (e.g. comments) will be lost. 

## Alternative packages
The beancount community offers a considerable array of add-on packages, many of which are well-rated and maintained. Below I've noted those I know of with functionality that includes some of what `beanahead` offers. Which package you're likely to find most useful will come down to your specific circumstances and requirements - horses for courses.
* [beancount-import](https://github.com/jbms/beancount-import) - an importer interface. Functionality provides for adding expected transactions directly to the main ledger and later merging these with imported transactions via a web-based UI. It requires implementing the importer interface and doesn't directly provide for regular expected transactions. But, if that import interface works for you then you'll probably want to be using `beancount-import`. (If you need the regular trasactions functionality provided by `beanahead`, just use `beanahead` to generate the transactions, copy them over to your ledger and let `beancount-import` handle the subsequent reconcilation.)

If you can recommend any other alternative package please raise a PR to add it here.

## `beancount` recommendations
If you don't already, it worth trying out a beancount syntax-highlighter extension. Have a look at the ['Editor Support' section of the Awesome Beancount](https://github.com/siddhantgoel/awesome-beancount#editor-support) repo to see if there's one available for your prefered editor.

More broadly, [awesome-beancount][awesome] is a great refrence for all things beancount. FWIW, these are my most-awesome of awesome-beancount:
* [Siddharnt Goel's blog post](https://sgoel.dev/posts/how-you-can-track-your-personal-finances-using-python/) uses `beancount` examples to explain Plain Text Accounting and double-entry accounting. A great introduction to these concepts.
* The [beancount mailing list](https://groups.google.com/g/beancount) is the place to look for answers and raise questions.
* [reds-rants](https://reds-rants.netlify.app/personal-finance/the-five-minute-ledger-update/) offers a comprehensive set of blogs on everything importing. It's tremendous.
* [smart_importer](https://github.com/beancount/smart_importer) offers import hooks that include one for auto-completion of postings based on machine-learning trained on past entries. Smart stuff indeed.
* [beancount-import](https://github.com/jbms/beancount-import) is an importer interface. If it works for you to be locked into an importer interface, this is a great one to be locked into.

## License

[MIT License][license]


[beancount]: https://github.com/beancount/beancount
[license]: https://github.com/maread99/beanahead/blob/master/LICENSE.txt
[rx_defs_initial]: ./examples/defs/rx_def.beancount
[beancount_example]: https://github.com/beancount/beancount/blob/master/examples/example.beancount
[rx_def_updated]: ./examples/defs/rx_def_updated.beancount
[x_ledger]: ./examples/recon/x.beancount
[awesome]: https://github.com/siddhantgoel/awesome-beancount
