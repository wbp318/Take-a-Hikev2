import React from 'react';
import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';

const TrailsListEntry = ({ trail }) => {
  return (
    <Link to={`/trailprofile/${trail.id}`}>
      <div className="profile-card">
        <div className="list-item-card">
          <img src={trail.thumbnail} />
          <h3>{trail.name}</h3>
          <div className="info-group">
            <p>City: {trail.city}</p>
          </div>
          <div className="info-group">
            <p>State: {trail.region}</p>
          </div>
          <div className="info-group">
            <p>Rating: {trail.rating}</p>
          </div>
        </div>
      </div>
    </Link>
  );
};

export default TrailsListEntry;
