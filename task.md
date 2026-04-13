The task is to build an MVP risk management dashboard visualizing most important
metrics relevant to book management, such as PnL curve, monetization, client yield,
and possibly PnL attribution. This task should not take you more than 3-4 hours.
Use of agents is not discouraged, but if they are, .md files should be a part of the
repository. You can submit your task a GitHub repository.

Simulation details:
In this setup, "we" as Finalto are showing prices to a set of clients, the clients
perform trades utilizing the bid/ask prices, and the exposure ends up on our
book. Client buys – we are short, client sells – we are long.

The requirements are as follows:
- Create a mock market data streamer streaming bid/ask price for a set of mock
instruments (mimicking our existing pricing feeds).
- Create mock trading activity of a set of clients seeing these prices (mimicking
clients actually trading with us).
- Creating a dashboard subscribing to these feeds and presenting this information
in an efficient manner.

What will not be evaluated:
- The exact logic of price generation and trading activity – random walks and
random processes are perfectly fine, you don't need to pay too much attention to
it unless you want to.
- Frontend solution – we're not hiring for a frontend position. The dashboard
doesn't need to be the prettiest, but it needs to be usable and functional. Bare
HTML views won't cut it, but which exact solution you choose for presenting the
data is up to you.
- The exact choice or complexity of the tracked metrics. They need to be
informative, relevant to book management and ideally interactive (hovering over
charts showing time / values), but you don't have to spend hours designing them

What will be evaluated:
- Reproducibility and ease of local installation – I want to be able to clone the
repository, install the dependencies easily and spin it up locally. The design has
to take into account other users needing access to the codebase too.
- Stability – the dashboard should be stable and not run into any errors
whatsoever.
- Performance – the dashboard should reflect the data as it comes real time from
the streamer and there shouldn't be any noticeable lag on the data as well as the
display side.
- Scalability – we are not looking for something to accommodate millions of price
updates and hundreds of thousands of trades here – don't overengineer for these
scales. But do feel free to experiment with the scale. What if we scale it 10x? Will
it jam the dashboard? Or should we introduce some throttling?
- Readability – the design and implementation has to be understandable to other
people with good Python knowledge. We're not looking to introduce Assembly to
gain 0.0000001ms in message decoding. Choose simplicity over over-
engineering where possible. Documentation is appreciated.
