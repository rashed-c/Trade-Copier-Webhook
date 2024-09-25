import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const PutCallRatioChart = ({ optionsData }) => {
  const [ratioData, setRatioData] = useState([]);

  useEffect(() => {
    const calculateRatio = () => {
      const newRatioData = optionsData.map(option => {
        const putVolume = option.put_volume || 0;
        const callVolume = option.call_volume || 0;
        const ratio = callVolume !== 0 ? putVolume / callVolume : 0;
        return {
          strike: option.strike_price,
          ratio: parseFloat(ratio.toFixed(2))
        };
      });
      setRatioData(newRatioData);
    };

    calculateRatio();
  }, [optionsData]);

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={ratioData}
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="strike" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="ratio" stroke="#8884d8" activeDot={{ r: 8 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PutCallRatioChart;
