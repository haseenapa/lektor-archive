'use strict';

var React = require('react');
var utils = require('../utils');
var i18n = require('../i18n');
var {BasicWidgetMixin} = require('./mixins');


var CheckboxesInputWidget = React.createClass({
  mixins: [BasicWidgetMixin],

  statics: {
    deserializeValue: function(value) {
      var rv = value.split(',').map(function(x) {
        return x.match(/^\s*(.*?)\s*$/)[1];
      });
      if (rv.length === 1 && rv[0] === '') {
        rv = [];
      }
      return rv;
    },

    serializeValue: function(value) {
      return value.join(', ');
    }
  },

  onChange: function(field, event) {
    var newValue = utils.flipSetValue(this.props.value,
                                      field, event.target.checked);
    if (this.props.onChange) {
      this.props.onChange(newValue)
    }
  },

  isActive: function(field) {
    for (var i = 0; i < this.props.value.length; i++) {
      if (this.props.value[i] === field) {
        return true;
      }
    }
    return false;
  },

  render: function() {
    var {className, value, type, ...otherProps} = this.props;
    className = (className || '') + ' checkbox';

    var choices = this.props.type.choices.map(function(item) {
      return (
        <div className={className} key={item[0]}>
          <label>
            <input type="checkbox"
              {...otherProps}
              checked={this.isActive(item[0])}
              onChange={this.onChange.bind(this, item[0])} />
            {i18n.trans(item[1])}
          </label>
        </div>
      );
    }.bind(this));
    return (
      <div className="checkboxes">
        {choices}
      </div>
    )
  }
});

var SelectInputWidget = React.createClass({
  mixins: [BasicWidgetMixin],

  onChange: function(event) {
    this.props.onChange(event.target.value);
  },

  render: function() {
    var {className, type, onChange, ...otherProps} = this.props;

    var choices = this.props.type.choices.map((item) => {
      return (
        <option key={item[0]} value={item[0]}>
          {i18n.trans(item[1])}
        </option>
      );
    });
    choices.unshift(
      <option key="" value="">{'----'}</option>
    );

    return (
      <div className="form-group">
        <div className={className}>
          <select
            className="form-control"
            onChange={onChange ? this.onChange : null}
            {...otherProps}>
            {choices}
          </select>
        </div>
      </div>
    )
  }
});


module.exports = {
  CheckboxesInputWidget: CheckboxesInputWidget,
  SelectInputWidget: SelectInputWidget,
};
