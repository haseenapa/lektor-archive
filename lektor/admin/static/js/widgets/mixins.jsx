var React = require('react');

var utils = require('../utils');
var {gettext} = utils;


function ValidationFailure(options) {
  this.message = options.message || gettext('Invalid input');
  this.type = options.type || 'error';
}

var BasicWidgetMixin = {
  propTypes: {
    value: React.PropTypes.any,
    type: React.PropTypes.object,
    placeholder: React.PropTypes.any,
    onChange: React.PropTypes.func
  },

  getValidationFailure: function() {
    if (this.getValidationFailureImpl) {
      return this.getValidationFailureImpl();
    }
    return null;
  }
}


module.exports = {
  ValidationFailure: ValidationFailure,
  BasicWidgetMixin: BasicWidgetMixin
};
