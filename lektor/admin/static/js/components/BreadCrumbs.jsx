'use strict';

var React = require('react');
var Router = require("react-router");
var {Link, RouteHandler} = Router;

var RecordState = require('../mixins/RecordState');
var utils = require('../utils');


var BreadCrumbs = React.createClass({
  mixins: [RecordState, Router.State],

  getInitialState: function() {
    return {
      recordPathInfo: null
    }
  },

  componentDidMount: function() {
    this._updateCrumbs();
  },

  componentWillReceiveProps: function(nextProps) {
    this._updateCrumbs();
  },

  isPreviewActive: function() {
    var routes = this.getRoutes();
    return routes.length > 0 && routes[routes.length - 1].name === 'preview';
  },

  _updateCrumbs: function() {
    var path = this.getRecordPath();
    if (path === null) {
      return;
    }

    utils.loadData('/pathinfo', {path: path})
      .then(function(resp) {
        this.setState({
          recordPathInfo: {
            path: path,
            segments: resp.segments
          }
        });
      }.bind(this));
  },

  render: function() {
    var crumbs = [];
    var target = this.isPreviewActive() ? 'preview' : 'edit';

    if (this.state.recordPathInfo != null) {
      crumbs = this.state.recordPathInfo.segments.map(function(item) {
        var urlPath = utils.fsToUrlPath(item.path);
        var label = item.label;
        var className = 'record-crumb';

        if (!item.exists) {
          label = item.id;
          className += ' missing-record-crumb';
        }

        return (
          <li key={item.path} className={className}>
            <Link to={target} params={{path: urlPath}}>{label}</Link>
          </li>
        );
      });
    }
    return (
      <div className="breadcrumbs">
        <ul className="breadcrumb">{crumbs}</ul>
      </div>
    );
  }
});

module.exports = BreadCrumbs;
