;((exports) => {
  const bufferAdder = maxLength => (original, newItem) => {
    let buffer = original;

    if (buffer.size === maxLength) {
      buffer = buffer.shift();
    }

    return buffer.push(newItem);
  };

  // keep an hour of data around
  const append = bufferAdder(1 * 60 * 60);

  // Inspired by https://www.npmjs.com/package/memoize-one
  const memoizeOne = (fn) => {
    let lastArgs;
    let lastResult;

    return (...args) => {
      if (lastArgs && args.length === lastArgs.length && args.every((arg, i) => lastArgs[i] === arg)) {
        return lastResult;
      }
      lastResult = fn(...args);
      lastArgs = args;
      return lastResult;
    };
  };

  const roundTo = (base, number) => base * Math.round(number / base);

  const granularities = {
    '1s': ({ timestamp }) => roundTo(1000, new Date(timestamp).valueOf()),
    '15s': ({ timestamp }) => roundTo(15000, new Date(timestamp).valueOf()),
    '30s': ({ timestamp }) => roundTo(30000, new Date(timestamp).valueOf()),
    '60s': ({ timestamp }) => roundTo(60000, new Date(timestamp).valueOf()),
  };

  const selectData = memoizeOne((stats, granularity) => {
    const keyFn = granularities[granularity];
    const ret = [];
    let lastKey;
    let lastStat = stats.get(0);

    for (let stat of stats) {
      const key = keyFn(stat);
      if (key === lastKey) continue;

      ret.push({
        timestamp: key,
        queued: stat.total_queued - lastStat.total_queued,
        processed: stat.total_processed - lastStat.total_processed,
      });

      lastKey = key;
      lastStat = stat;
    }

    return ret;
  });

  const reducer = (stats, action) => {
    switch (action.type) {
      case 'RECEIVE_STATS':
        return append(stats, action.payload);
      default:
        throw new Error(`Unknown action type (${action.type})`);
    }
  };

  const tickFormatter = (tick) => {
    if (tick === Infinity || tick === -Infinity) return '';

    return new Date(tick).toISOString();
  };

  const initialState = Immutable.List();

  const BigNumber = ({ value, label, ...props }) =>
    <div
      style={{
        textAlign: 'center',
        ...(props.style || {}),
      }}
      {...props}
    >
      <h2>{value}</h2>
      <label>{label}</label>
    </div>

  const Chart = ({ stats }) => {
    const [granularity, setGranularity] = React.useState(undefined);
    const effectiveGranularity = (
      granularity
      || (stats.size >= 60 * 3 && '60s')
      || (stats.size >= 30 * 3 && '30s')
      || (stats.size >= 15 * 3 && '15s')
      || '1s'
    );

    return (
      <>
        <Recharts.ResponsiveContainer
          width="100%"
          height={400}
        >
          <Recharts.LineChart
            data={selectData(stats, effectiveGranularity)}
            margin={{
              top: 5, right: 30, left: 20, bottom: 5,
            }}
          >
            <Recharts.CartesianGrid strokeDasharray="3 3" />
            <Recharts.XAxis
              dataKey="timestamp"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={tickFormatter}
            />
            <Recharts.YAxis
              label={`jobs/${effectiveGranularity}`}
            />
            <Recharts.Tooltip />
            <Recharts.Legend />
            <Recharts.Line type="monotone" dataKey="queued" stroke="#8884d8" isAnimationActive={false} />
            <Recharts.Line type="monotone" dataKey="processed" stroke="#82ca9d" isAnimationActive={false} />
          </Recharts.LineChart>
        </Recharts.ResponsiveContainer>
        <button disabled={granularity === undefined} onClick={() => setGranularity(undefined)}>default</button>
        <button disabled={granularity === '1s'} onClick={() => setGranularity('1s')}>1s</button>
        <button disabled={granularity === '15s'} onClick={() => setGranularity('15s')}>15s</button>
        <button disabled={granularity === '30s'} onClick={() => setGranularity('30s')}>30s</button>
        <button disabled={granularity === '60s'} onClick={() => setGranularity('60s')}>60s</button>
      </>
    );
  };

  const App = ({
    apiUrl,
    pollMs = 1000,
  }) => {
    const [stats, dispatch] = React.useReducer(reducer, initialState);

    React.useEffect(() => {
      let timeoutId;

      const fetchAndRepeat = async () => {
        const resp = await fetch(apiUrl);
        const stats = await resp.json();

        dispatch({
          type: 'RECEIVE_STATS',
          payload: stats,
        });

        setTimeout(fetchAndRepeat, pollMs);
      }

      fetchAndRepeat();

      return () => clearTimeout(timeoutId);
    }, [pollMs]);

    const lastState = stats.last();

    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-evenly' }}>
          <BigNumber
            value={lastState ? lastState.enqueued : 0}
            label="enqueued"
          />
          <BigNumber
            value={lastState ? lastState.scheduled : 0}
            label="scheduled"
          />
        </div>
        <Chart stats={stats} />
      </div>
    );
  };

  exports.Dashboard = {
    init({ apiUrl }) {
      ReactDOM.render(
        <App
          pollMs={1000}
          apiUrl={apiUrl}
        />,
        document.getElementById('root'),
      );
    },
  };
})(window);
